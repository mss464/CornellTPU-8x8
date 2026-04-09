`timescale 1 ns / 1 ps
// ============================================================================
// mem_ctrl.sv — Memory Controller FSM
//
// Handles four doorbell-driven modes:
//   1 = DMA_WRITE  : Host → System Memory  (AXI-Stream slave writes)
//   2 = DMA_READ   : System Memory → Host  (AXI-Stream master reads)
//   5 = SYS_TO_OC  : System Memory → On-Chip Memory (32-bit word copy)
//   6 = OC_TO_SYS  : On-Chip Memory → System Memory (32-bit word copy)
//
// Modes 3/4 (AXI-Full MMIO) bypass this FSM entirely — the AXI-Full slave
// port is hard-wired to sys_mem Port B.
//
// Interface contract:
//   - `start` is a 1-cycle pulse; addresses & length latched at that moment
//   - `done`  is a 1-cycle pulse on transfer completion
//   - `stream_ready` mirrors readiness for DMA write path
// ============================================================================
module mem_ctrl (
    input  wire        clk,
    input  wire        rst_n,

    // ── Arbiter dispatch ─────────────────────────────────────────────
    input  wire        start,          // 1-cycle pulse
    input  wire [3:0]  mode,           // mode to execute
    output reg         done,           // 1-cycle completion pulse

    // ── DMA address / length from AXI-Lite registers ─────────────────
    input  wire [15:0] addr_sys_in,    // system memory base (word addr)
    input  wire [14:0] addr_oc_in,     // on-chip memory base (word addr)
    input  wire [31:0] length_in,      // transfer length (32-bit words)

    // ── Stream-ready status (→ AXI-Lite 0x08) ────────────────────────
    output reg         stream_ready,

    // ── AXI-Stream slave (DMA write) control ─────────────────────────
    input  wire [15:0] write_pointer,  // from stream slave
    output reg         data_write_en,  // enable sys_mem DMA write

    // ── AXI-Stream master (DMA read) control ─────────────────────────
    output reg         start_stream,   // kick master stream
    output reg         read_en,        // enable sys_mem DMA read

    // ── Completion from AXI-Stream modules ───────────────────────────
    input  wire        write_bram_done,
    input  wire        read_bram_done,

    // ── System Memory Port B (scalar, 32-bit) ────────────────────────
    // Used for sys↔onchip copies (muxed with AXI-Full in mem_top)
    output reg  [15:0] sys_scalar_addr,
    output reg  [31:0] sys_scalar_din,
    input  wire [31:0] sys_scalar_dout,
    output reg         sys_scalar_en,
    output reg         sys_scalar_we,

    // ── On-Chip Memory Port A (32-bit) ───────────────────────────────
    output reg  [14:0] oc_addr,
    output reg  [31:0] oc_din,
    input  wire [31:0] oc_dout,
    output reg         oc_en,
    output reg         oc_we
);

    // Mode constants
    localparam MODE_DMA_WRITE = 4'd1;
    localparam MODE_DMA_READ  = 4'd2;
    localparam MODE_SYS_TO_OC = 4'd5;
    localparam MODE_OC_TO_SYS = 4'd6;

    // FSM states
    localparam [2:0] S_IDLE        = 3'd0,
                     S_DMA_WRITE   = 3'd1,
                     S_DMA_READ    = 3'd2,
                     S_SYS2OC_RD   = 3'd3,  // read from sys_mem
                     S_SYS2OC_WR   = 3'd4,  // write to onchip_mem
                     S_OC2SYS_RD   = 3'd5,  // read from onchip_mem
                     S_OC2SYS_WR   = 3'd6;  // write to sys_mem

    reg [2:0]  state;
    reg [3:0]  latched_mode;
    reg [15:0] latched_sys_addr;
    reg [14:0] latched_oc_addr;
    reg [15:0] latched_length;
    reg [15:0] word_cnt;

    // Pipeline registers for BRAM read latency (1 cycle)
    reg        prev_sys_rd;
    reg        prev_oc_rd;
    reg [31:0] captured_data;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state            <= S_IDLE;
            done             <= 1'b0;
            stream_ready     <= 1'b1;
            data_write_en    <= 1'b0;
            start_stream     <= 1'b0;
            read_en          <= 1'b0;
            latched_mode     <= 4'd0;
            latched_sys_addr <= 16'd0;
            latched_oc_addr  <= 15'd0;
            latched_length   <= 16'd0;
            word_cnt         <= 16'd0;
            sys_scalar_addr  <= 16'd0;
            sys_scalar_din   <= 32'd0;
            sys_scalar_en    <= 1'b0;
            sys_scalar_we    <= 1'b0;
            oc_addr          <= 15'd0;
            oc_din           <= 32'd0;
            oc_en            <= 1'b0;
            oc_we            <= 1'b0;
            prev_sys_rd      <= 1'b0;
            prev_oc_rd       <= 1'b0;
            captured_data    <= 32'd0;
        end else begin
            // Pulse defaults
            done            <= 1'b0;
            data_write_en   <= 1'b0;
            start_stream    <= 1'b0;
            read_en         <= 1'b0;
            sys_scalar_en   <= 1'b0;
            sys_scalar_we   <= 1'b0;
            oc_en           <= 1'b0;
            oc_we           <= 1'b0;

            // Pipeline tracking
            prev_sys_rd     <= (sys_scalar_en && !sys_scalar_we);
            prev_oc_rd      <= (oc_en && !oc_we);

            case (state)
                // =============================================================
                S_IDLE: begin
                    stream_ready <= 1'b1;
                    if (start) begin
                        latched_mode     <= mode;
                        latched_sys_addr <= addr_sys_in;
                        latched_oc_addr  <= addr_oc_in;
                        latched_length   <= length_in[15:0];
                        word_cnt         <= 16'd0;
                        case (mode)
                            MODE_DMA_WRITE: begin
                                data_write_en <= 1'b1;
                                stream_ready  <= 1'b1;
                                state         <= S_DMA_WRITE;
                            end
                            MODE_DMA_READ: begin
                                read_en      <= 1'b1;
                                start_stream <= 1'b1;
                                stream_ready <= 1'b1;
                                state        <= S_DMA_READ;
                            end
                            MODE_SYS_TO_OC: begin
                                state <= S_SYS2OC_RD;
                            end
                            MODE_OC_TO_SYS: begin
                                state <= S_OC2SYS_RD;
                            end
                            default: begin
                                done <= 1'b1;
                            end
                        endcase
                    end
                end

                // =============================================================
                // DMA Write: keep data_write_en asserted until stream completes
                // =============================================================
                S_DMA_WRITE: begin
                    stream_ready  <= 1'b1;
                    data_write_en <= 1'b1;
                    if (write_bram_done) begin
                        state <= S_IDLE;
                        done  <= 1'b1;
                    end
                end

                // =============================================================
                // DMA Read: keep read_en asserted until stream completes
                // =============================================================
                S_DMA_READ: begin
                    stream_ready <= 1'b1;
                    read_en      <= 1'b1;
                    if (read_bram_done) begin
                        state <= S_IDLE;
                        done  <= 1'b1;
                    end
                end

                // =============================================================
                // System Memory → On-Chip Memory
                //   Step 1: Issue read from sys_mem Port B
                //   Step 2: Capture data, write to on-chip Port A
                // =============================================================
                S_SYS2OC_RD: begin
                    if (word_cnt < latched_length) begin
                        // Issue read from system memory
                        sys_scalar_addr <= latched_sys_addr + word_cnt;
                        sys_scalar_en   <= 1'b1;
                        // sys_scalar_we stays 0 (read)
                        state           <= S_SYS2OC_WR;
                    end else begin
                        state <= S_IDLE;
                        done  <= 1'b1;
                    end
                end

                S_SYS2OC_WR: begin
                    if (prev_sys_rd) begin
                        // Data from sys_mem is valid — write to on-chip
                        oc_addr  <= latched_oc_addr + word_cnt[14:0];
                        oc_din   <= sys_scalar_dout;
                        oc_en    <= 1'b1;
                        oc_we    <= 1'b1;
                        word_cnt <= word_cnt + 16'd1;
                        state    <= S_SYS2OC_RD;
                    end
                    // else: wait for BRAM read latency
                end

                // =============================================================
                // On-Chip Memory → System Memory
                //   Step 1: Issue read from on-chip Port A
                //   Step 2: Capture data, write to sys_mem Port B
                // =============================================================
                S_OC2SYS_RD: begin
                    if (word_cnt < latched_length) begin
                        // Issue read from on-chip memory
                        oc_addr <= latched_oc_addr + word_cnt[14:0];
                        oc_en   <= 1'b1;
                        // oc_we stays 0 (read)
                        state   <= S_OC2SYS_WR;
                    end else begin
                        state <= S_IDLE;
                        done  <= 1'b1;
                    end
                end

                S_OC2SYS_WR: begin
                    if (prev_oc_rd) begin
                        // Data from on-chip is valid — write to sys_mem
                        sys_scalar_addr <= latched_sys_addr + word_cnt;
                        sys_scalar_din  <= oc_dout;
                        sys_scalar_en   <= 1'b1;
                        sys_scalar_we   <= 1'b1;
                        word_cnt        <= word_cnt + 16'd1;
                        state           <= S_OC2SYS_RD;
                    end
                    // else: wait for BRAM read latency
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
