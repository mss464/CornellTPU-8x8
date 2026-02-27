`timescale 1 ns / 1 ps
// ============================================================================
// dma_engine.sv — DMA / host-transfer sub-FSM (P2.08)
//
// Owns:
//   - AXI-Stream slave control (modes 1/4: write to devmem / IRAM)
//   - AXI-Stream master control (mode 2: read from devmem)
//   - L2 host-controlled block transfers (modes 5/6: DM↔L2 via tma_engine)
//   - IRAM address counter (mode 4 only)
//
// Resource footprint:
//   - device_mem Port A (modes 1/2)
//   - l2_tile host-transfer ports — dm_* wires on device_mem Port B + l2_tile
//     Port B; this is the tma_engine FSM inside l2_tile (modes 5/6)
//   - tpu_slave_axi_stream / tpu_master_axi_stream
//
// Concurrent safety:
//   dma_engine uses device_mem Port A and the AXI-Stream path. compute_ctrl
//   and l2_ctrl use separate BRAM ports. All three sub-FSMs may run
//   simultaneously without resource conflicts.
//   Exception: MODE_WR_IRAM (4) shares the IRAM with MODE_COMPUTE (3).
//   Software contract: do not issue mode-4 while mode-3 is executing.
//
// Interface contract:
//   - `start`  is a 1-cycle pulse from the arbiter; addresses and length are
//     latched at that moment for the duration of the transfer.
//   - `done`   is a 1-cycle pulse on transfer completion.
//   - `stream_ready` is high whenever the AXI-Stream write path is open,
//     matching the semantics expected by the host driver at offset 0x08.
// ============================================================================
module dma_engine (
    input  wire        clk,
    input  wire        rst_n,

    // Arbiter dispatch
    input  wire        start,         // 1-cycle pulse from arbiter
    input  wire [3:0]  mode,          // mode to execute (latched on start)
    // Addresses live-wired from AXI-Lite registers (seen by device_mem / l2_tile)
    input  wire [7:0]  addr_ram_in,   // IRAM base (addr_ram[7:0]) — used for iram_addr
    input  wire [15:0] write_pointer, // current write pointer from slave stream
    output reg         done,          // 1-cycle pulse on completion

    // Stream-ready status (→ AXI-Lite 0x08)
    output reg         stream_ready,

    // AXI-Stream slave (DMA write) control
    output reg         data_write_en,
    output reg         instr_write_en,

    // AXI-Stream master (DMA read) control
    output reg         start_stream,
    output reg         read_en,

    // IRAM address counter output (→ compute_tile.iram_addr)
    output reg  [7:0]  iram_addr,

    // Completion inputs from AXI-Stream modules
    input  wire        write_bram_done,
    input  wire        read_bram_done,

    // L2 host-controlled transfer (modes 5/6 — through l2_tile's tma_engine)
    output reg         start_dm_to_l2,
    output reg         start_l2_to_dm,
    input  wire        xfer_l2_done
);

    localparam MODE_WR_DEVMEM = 4'd1;
    localparam MODE_RD_DEVMEM = 4'd2;
    localparam MODE_WR_IRAM   = 4'd4;
    localparam MODE_DM2L2     = 4'd5;
    localparam MODE_L22DM     = 4'd6;

    localparam DE_IDLE    = 3'd0;
    localparam DE_WRITE   = 3'd1;  // modes 1 and 4
    localparam DE_READ    = 3'd2;  // mode  2
    localparam DE_DM2L2   = 3'd3;  // mode  5
    localparam DE_L22DM   = 3'd4;  // mode  6

    reg [2:0] state;
    reg [3:0] latched_mode;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state          <= DE_IDLE;
            done           <= 1'b0;
            stream_ready   <= 1'b1;
            data_write_en  <= 1'b0;
            instr_write_en <= 1'b0;
            start_stream   <= 1'b0;
            read_en        <= 1'b0;
            start_dm_to_l2 <= 1'b0;
            start_l2_to_dm <= 1'b0;
            latched_mode   <= 4'd0;
            iram_addr      <= 8'd0;
        end else begin
            // Pulse defaults
            done           <= 1'b0;
            data_write_en  <= 1'b0;
            instr_write_en <= 1'b0;
            start_stream   <= 1'b0;
            read_en        <= 1'b0;
            start_dm_to_l2 <= 1'b0;
            start_l2_to_dm <= 1'b0;

            case (state)
                //--------------------------------------------------------------
                DE_IDLE: begin
                    stream_ready <= 1'b1;
                    if (start) begin
                        latched_mode <= mode;
                        case (mode)
                            MODE_WR_DEVMEM: begin
                                data_write_en <= 1'b1;
                                stream_ready  <= 1'b1;
                                state         <= DE_WRITE;
                            end
                            MODE_WR_IRAM: begin
                                instr_write_en <= 1'b1;
                                stream_ready   <= 1'b1;
                                state          <= DE_WRITE;
                            end
                            MODE_RD_DEVMEM: begin
                                read_en      <= 1'b1;
                                start_stream <= 1'b1;
                                stream_ready <= 1'b1;
                                state        <= DE_READ;
                            end
                            MODE_DM2L2: begin
                                start_dm_to_l2 <= 1'b1;
                                state          <= DE_DM2L2;
                            end
                            MODE_L22DM: begin
                                start_l2_to_dm <= 1'b1;
                                state          <= DE_L22DM;
                            end
                            default: begin
                                done <= 1'b1; // unknown mode — nop
                            end
                        endcase
                    end
                end

                //--------------------------------------------------------------
                // Keep write_en asserted throughout the DMA write transfer.
                // IRAM address counter is updated here (mode 4 only).
                DE_WRITE: begin
                    stream_ready <= 1'b1;
                    if (latched_mode == MODE_WR_DEVMEM) begin
                        data_write_en <= 1'b1;
                    end else if (latched_mode == MODE_WR_IRAM) begin
                        instr_write_en <= 1'b1;
                        // Update IRAM address: addr_ram + upper bits of write_pointer.
                        // write_pointer advances by 1 per 32-bit word; IRAM is 64-bit,
                        // so pairs map to one address. write_pointer[0] toggles each pair.
                        if (instr_write_en && write_pointer[0])
                            iram_addr <= addr_ram_in + write_pointer[7:1];
                    end
                    if (write_bram_done) begin
                        state <= DE_IDLE;
                        done  <= 1'b1;
                    end
                end

                //--------------------------------------------------------------
                DE_READ: begin
                    stream_ready <= 1'b1;
                    read_en <= 1'b1;
                    if (read_bram_done) begin
                        state <= DE_IDLE;
                        done  <= 1'b1;
                    end
                end

                //--------------------------------------------------------------
                DE_DM2L2: begin
                    if (xfer_l2_done) begin
                        state <= DE_IDLE;
                        done  <= 1'b1;
                    end
                end

                DE_L22DM: begin
                    if (xfer_l2_done) begin
                        state <= DE_IDLE;
                        done  <= 1'b1;
                    end
                end

                default: state <= DE_IDLE;
            endcase
        end
    end

endmodule
