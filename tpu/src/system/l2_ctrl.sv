`timescale 1 ns / 1 ps
// ============================================================================
// l2_ctrl.sv — L2↔L1 burst transfer sub-FSM (P2.08)
//
// Owns: L2 tile Port A (ct_addr/en/we/din/dout) and L1 DMA port
//       (l1_dma_wr/rd_en, _data, _ptr).
//
// Handled modes:
//   7 = L22L1  — read L2 at (addr_l2 + offset), write L1 DMA port
//   8 = L12L2  — read L1 DMA port, write L2 at (addr_l2 + offset)
//
// BRAM timing: 1-cycle registered output.
//   L22L1: on cycle N issue L2 read → data valid on cycle N+1 (l2l1_rd_valid).
//   L12L2: on cycle N issue L1 read → data valid on cycle N+1 → write L2.
//
// Concurrent safety:
//   L2 Port A (this module) and L2 Port B (tma_engine, DMA modes 5/6) are
//   separate dual-port BRAM accesses — no conflict at the BRAM level.
//   L1 Port A (this module) and L1 Port B (tensorcore / compute_ctrl) are
//   also separate — no conflict.
//   => l2_ctrl can run concurrently with dma_engine and compute_ctrl.
//
// Interface contract:
//   - `start` is a 1-cycle pulse. addr_l2/length are latched at that moment.
//   - `done`  is a 1-cycle pulse on transfer completion.
// ============================================================================
module l2_ctrl (
    input  wire        clk,
    input  wire        rst_n,

    // Arbiter dispatch
    input  wire        start,          // 1-cycle pulse from arbiter
    input  wire [3:0]  mode,           // MODE_L22L1 or MODE_L12L2 (latched on start)
    input  wire [14:0] addr_l2_in,     // L2 base address (latched on start)
    input  wire [31:0] length_in,      // transfer length in words (latched on start)
    output reg         done,           // 1-cycle pulse on completion

    // L2 tile Port A (compute-tile side)
    output wire [14:0] l2_ct_addr,
    output wire        l2_ct_en,
    output wire        l2_ct_we,
    output wire [31:0] l2_ct_din,
    input  wire [31:0] l2_ct_dout,

    // L1 DMA port (compute_tile Port A)
    output wire        l1_dma_wr_en,
    output wire [31:0] l1_dma_wr_data,
    output wire [15:0] l1_dma_write_ptr,
    output wire        l1_dma_rd_en,
    input  wire [31:0] l1_dma_rd_data,
    output wire [15:0] l1_dma_read_ptr
);

    localparam MODE_L22L1 = 4'd7;
    localparam MODE_L12L2 = 4'd8;

    localparam LC_IDLE  = 2'd0;
    localparam LC_L22L1 = 2'd1;
    localparam LC_L12L2 = 2'd2;

    reg [1:0]  state;
    reg [3:0]  latched_mode;
    reg [14:0] latched_addr_l2;
    reg [15:0] latched_length;

    reg [15:0] l2l1_rd_issued; // number of read-address cycles issued
    reg        l2l1_rd_valid;  // data from previous read is valid this cycle
    reg [15:0] l2l1_wr_ptr;   // write-address offset (1 cycle behind rd_issued)

    // -------------------------------------------------------------------------
    // Combinational L2 Port A drive
    // -------------------------------------------------------------------------
    assign l2_ct_addr = (state == LC_L22L1)
                          ? (latched_addr_l2 + l2l1_rd_issued[14:0])
                          : (state == LC_L12L2)
                              ? (latched_addr_l2 + l2l1_wr_ptr[14:0])
                              : 15'b0;

    assign l2_ct_en   = (state == LC_L22L1 && l2l1_rd_issued < latched_length) ||
                        (state == LC_L12L2  && l2l1_rd_valid);

    assign l2_ct_we   = (state == LC_L12L2  && l2l1_rd_valid);
    assign l2_ct_din  = l1_dma_rd_data;  // L1 read data → L2 write

    // -------------------------------------------------------------------------
    // Combinational L1 DMA port drive
    // -------------------------------------------------------------------------
    assign l1_dma_wr_en      = (state == LC_L22L1 && l2l1_rd_valid);
    assign l1_dma_wr_data    = l2_ct_dout;       // L2 read data → L1 write
    assign l1_dma_write_ptr  = l2l1_wr_ptr;

    assign l1_dma_rd_en      = (state == LC_L12L2 && l2l1_rd_issued < latched_length);
    assign l1_dma_read_ptr   = {3'b0, l2l1_rd_issued[12:0]};

    // -------------------------------------------------------------------------
    // Sequential FSM
    // -------------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state           <= LC_IDLE;
            done            <= 1'b0;
            latched_mode    <= 4'd0;
            latched_addr_l2 <= 15'd0;
            latched_length  <= 16'd0;
            l2l1_rd_issued  <= 16'd0;
            l2l1_rd_valid   <= 1'b0;
            l2l1_wr_ptr     <= 16'd0;
        end else begin
            done          <= 1'b0;
            l2l1_rd_valid <= 1'b0;

            case (state)
                LC_IDLE: begin
                    if (start) begin
                        latched_mode    <= mode;
                        latched_addr_l2 <= addr_l2_in;
                        latched_length  <= length_in[15:0];
                        l2l1_rd_issued  <= 16'd0;
                        l2l1_rd_valid   <= 1'b0;
                        l2l1_wr_ptr     <= 16'd0;
                        case (mode)
                            MODE_L22L1: state <= LC_L22L1;
                            MODE_L12L2: state <= LC_L12L2;
                            default:    done  <= 1'b1; // unknown mode — nop
                        endcase
                    end
                end

                // L2 → L1: issue reads from L2 Port A into L1 DMA port.
                // Read address issued on cycle N → data valid on cycle N+1 (rd_valid).
                LC_L22L1: begin
                    if (l2l1_rd_issued < latched_length) begin
                        l2l1_rd_valid  <= 1'b1;
                        l2l1_wr_ptr    <= l2l1_rd_issued;
                        l2l1_rd_issued <= l2l1_rd_issued + 16'd1;
                    end
                    // Done when the last rd_valid write has been committed.
                    if (l2l1_rd_issued >= latched_length) begin
                        state <= LC_IDLE;
                        done  <= 1'b1;
                    end
                end

                // L1 → L2: issue reads from L1 DMA port into L2 Port A.
                // Same pipeline: read issued N → data valid N+1 → write L2.
                LC_L12L2: begin
                    if (l2l1_rd_issued < latched_length) begin
                        l2l1_rd_valid  <= 1'b1;
                        l2l1_wr_ptr    <= l2l1_rd_issued;
                        l2l1_rd_issued <= l2l1_rd_issued + 16'd1;
                    end
                    if (l2l1_rd_issued >= latched_length) begin
                        state <= LC_IDLE;
                        done  <= 1'b1;
                    end
                end

                default: state <= LC_IDLE;
            endcase
        end
    end

endmodule
