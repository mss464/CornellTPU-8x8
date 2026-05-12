`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// tma_engine.sv — LPDDR4-aware TMA engine
//
// Tensor Memory Access (TMA) engine.
// Handles burst block copies between L2 SRAM and Device Memory.
//
// Updated for AXI4-based device_mem: uses dm_ready/dm_rvalid/dm_bvalid
// handshake instead of assuming fixed 1-cycle BRAM latency.
//
// Two request sources (mutually exclusive in practice):
//   - Host-controlled (from tpu.sv modes 5/6):
//       start_dm_to_l2 / start_l2_to_dm with host_dm_base/host_l2_base/host_len
//   - TMA instruction (from tensorcore via l2_tile):
//       tma_req + tma_dir + tma_dm_base/tma_l2_base/tma_len
//
// Priority: TMA instruction wins if both arrive simultaneously in IDLE.
//
// Transfer FSM:
//   DM2L2_READ  — issue devmem read, wait for dm_rvalid
//   DM2L2_WRITE — write returned data to L2, advance or finish
//   L22DM_READ  — issue L2 SRAM read (1-cycle latency)
//   L22DM_WRITE — write L2 data to devmem, wait for dm_bvalid
//   DONE        — assert done, return to IDLE
//////////////////////////////////////////////////////////////////////////////////

module tma_engine #(
    parameter L2_ADDR_WIDTH  = 15,   // 32768 words
    parameter DATA_WIDTH     = 32,
    parameter DM_ADDR_WIDTH  = 16    // device memory address width
)(
    input  logic clk,
    input  logic rst_n,

    // === Host-controlled transfer (from tpu.sv FSM, modes 5/6) ===
    input  logic                      start_dm_to_l2,
    input  logic                      start_l2_to_dm,
    input  logic [DM_ADDR_WIDTH-1:0]  host_dm_base,
    input  logic [L2_ADDR_WIDTH-1:0]  host_l2_base,
    input  logic [15:0]               host_len,
    output logic                      host_done,     // 1-cycle pulse on host transfer complete

    // === TMA instruction port (from tensorcore via l2_tile) ===
    input  logic                      tma_req,       // 1-cycle pulse: start TMA transfer
    input  logic                      tma_dir,       // 0=DM_TO_L2, 1=L2_TO_DM
    input  logic [DM_ADDR_WIDTH-1:0]  tma_dm_base,
    input  logic [L2_ADDR_WIDTH-1:0]  tma_l2_base,
    input  logic [15:0]               tma_len,
    output logic                      tma_done,      // 1-cycle pulse on TMA transfer complete

    // === L2 SRAM Port B ===
    output logic [L2_ADDR_WIDTH-1:0]  sram_addr_b,
    output logic [DATA_WIDTH-1:0]     sram_din_b,
    input  logic [DATA_WIDTH-1:0]     sram_dout_b,
    output logic                      sram_en_b,
    output logic                      sram_we_b,

    // === DevMem Port B (now AXI-backed) ===
    output logic [DM_ADDR_WIDTH-1:0]  dm_addr,
    output logic [DATA_WIDTH-1:0]     dm_din,
    input  logic [DATA_WIDTH-1:0]     dm_dout,
    output logic                      dm_en,
    output logic                      dm_we,
    input  logic                      dm_ready,    // AXI ready for new command
    input  logic                      dm_rvalid,   // AXI read data valid
    input  logic                      dm_bvalid    // AXI write response valid
);

    // =========================================================================
    // Transfer FSM
    // =========================================================================
    typedef enum logic [2:0] {
        IDLE        = 3'd0,
        DM2L2_READ  = 3'd1,   // issue devmem read, wait for rvalid
        DM2L2_WRITE = 3'd2,   // write returned data to L2
        L22DM_READ  = 3'd3,   // issue L2 read (1-cycle BRAM latency)
        L22DM_WRITE = 3'd4,   // write L2 data to devmem, wait for bvalid
        DONE        = 3'd5
    } xfer_state_t;

    xfer_state_t state;

    // Transfer parameter registers (latched on start)
    logic [15:0]               xfer_count;
    logic [15:0]               len_reg;
    logic [DM_ADDR_WIDTH-1:0]  dm_base_reg;
    logic [L2_ADDR_WIDTH-1:0]  l2_base_reg;
    logic                      source_is_tma; // 0=host, 1=TMA instruction

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state         <= IDLE;
            host_done     <= 1'b0;
            tma_done      <= 1'b0;
            xfer_count    <= 16'd0;
            len_reg       <= 16'd0;
            dm_base_reg   <= '0;
            l2_base_reg   <= '0;
            source_is_tma <= 1'b0;
        end else begin
            // Pulsed outputs — deassert by default
            host_done   <= 1'b0;
            tma_done    <= 1'b0;

            case (state)
                // ---- IDLE: wait for a request ----
                IDLE: begin
                    xfer_count <= 16'd0;
                    // TMA instruction has priority over host request
                    if (tma_req) begin
                        source_is_tma <= 1'b1;
                        dm_base_reg   <= tma_dm_base;
                        l2_base_reg   <= tma_l2_base;
                        len_reg       <= tma_len;
                        state         <= tma_dir ? L22DM_READ : DM2L2_READ;
                    end else if (start_dm_to_l2) begin
                        source_is_tma <= 1'b0;
                        dm_base_reg   <= host_dm_base;
                        l2_base_reg   <= host_l2_base;
                        len_reg       <= host_len;
                        state         <= DM2L2_READ;
                    end else if (start_l2_to_dm) begin
                        source_is_tma <= 1'b0;
                        dm_base_reg   <= host_dm_base;
                        l2_base_reg   <= host_l2_base;
                        len_reg       <= host_len;
                        state         <= L22DM_READ;
                    end
                end

                // ---- DevMem → L2: Read from devmem (wait for AXI response) ----
                DM2L2_READ: begin
                    // Wait for dm_rvalid — data is now on dm_dout
                    if (dm_rvalid) begin
                        state <= DM2L2_WRITE;
                    end
                end

                // ---- DevMem → L2: Write returned data to L2 SRAM ----
                DM2L2_WRITE: begin
                    // L2 SRAM write completes in 1 cycle (BRAM)
                    xfer_count <= xfer_count + 16'd1;
                    if (xfer_count + 1 >= len_reg) begin
                        state <= DONE;
                    end else begin
                        state <= DM2L2_READ; // next word
                    end
                end

                // ---- L2 → DevMem: Read from L2 SRAM (1-cycle BRAM) ----
                L22DM_READ: begin
                    // BRAM read issued this cycle; data available next cycle
                    state <= L22DM_WRITE;
                end

                // ---- L2 → DevMem: Write to devmem (wait for AXI response) ----
                L22DM_WRITE: begin
                    // Wait for dm_bvalid — write accepted
                    if (dm_bvalid) begin
                        xfer_count <= xfer_count + 16'd1;
                        if (xfer_count + 1 >= len_reg) begin
                            state <= DONE;
                        end else begin
                            state <= L22DM_READ; // next word
                        end
                    end
                end

                // ---- Done: assert appropriate completion signal ----
                DONE: begin
                    if (source_is_tma)
                        tma_done <= 1'b1;
                    else
                        host_done <= 1'b1;
                    state <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end

    // =========================================================================
    // Combinational output mux for SRAM Port B and DevMem signals
    // =========================================================================
    always_comb begin
        // Defaults — no activity
        sram_addr_b = '0;
        sram_din_b  = '0;
        sram_en_b   = 1'b0;
        sram_we_b   = 1'b0;
        dm_addr     = '0;
        dm_din      = '0;
        dm_en       = 1'b0;
        dm_we       = 1'b0;

        case (state)
            DM2L2_READ: begin
                // Issue read to devmem at current offset
                dm_addr = dm_base_reg + xfer_count[DM_ADDR_WIDTH-1:0];
                dm_en   = 1'b1;
                dm_we   = 1'b0;
            end

            DM2L2_WRITE: begin
                // Write devmem read result to L2 SRAM
                sram_addr_b = l2_base_reg + xfer_count[L2_ADDR_WIDTH-1:0];
                sram_din_b  = dm_dout;
                sram_en_b   = 1'b1;
                sram_we_b   = 1'b1;
            end

            L22DM_READ: begin
                // Issue read to L2 SRAM at current offset
                sram_addr_b = l2_base_reg + xfer_count[L2_ADDR_WIDTH-1:0];
                sram_en_b   = 1'b1;
                sram_we_b   = 1'b0;
            end

            L22DM_WRITE: begin
                // Write L2 read result to devmem
                dm_addr = dm_base_reg + xfer_count[DM_ADDR_WIDTH-1:0];
                dm_din  = sram_dout_b;
                dm_en   = 1'b1;
                dm_we   = 1'b1;
            end

            default: ;
        endcase
    end

endmodule
