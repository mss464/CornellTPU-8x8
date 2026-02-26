`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// tma_engine.sv
//
// Tensor Memory Access (TMA) engine.
// Handles burst block copies between L2 SRAM and Device Memory.
//
// Two request sources (mutually exclusive in practice):
//   - Host-controlled (from tpu.sv modes 5/6):
//       start_dm_to_l2 / start_l2_to_dm with host_dm_base/host_l2_base/host_len
//   - TMA instruction (from tensorcore via l2_tile):
//       tma_req + tma_dir + tma_dm_base/tma_l2_base/tma_len
//
// Priority: TMA instruction wins if both arrive simultaneously in IDLE.
//
// Completion:
//   - host_done: asserted 1 cycle when host-triggered transfer finishes
//   - tma_done:  asserted 1 cycle when TMA-instruction-triggered transfer finishes
//
// Transfer FSM:
//   DM2L2_READ  — issuing devmem reads; pipelining L2 writes
//   DM2L2_WRITE — draining last devmem → L2 write
//   L22DM_READ  — issuing L2 reads; pipelining devmem writes
//   L22DM_WRITE — draining last L2 → devmem write
//   DONE        — assert done, return to IDLE
//
// Timing: 1-cycle BRAM read latency is accounted for by the READ→WRITE pipeline.
//   Read N:   issue read at addr N  (dm_addr/sram_addr_b driven combinationally)
//   Read N+1: write data from read N to destination (rd_valid_d1 pipeline)
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

    // === DevMem Port B ===
    output logic [DM_ADDR_WIDTH-1:0]  dm_addr,
    output logic [DATA_WIDTH-1:0]     dm_din,
    input  logic [DATA_WIDTH-1:0]     dm_dout,
    output logic                      dm_en,
    output logic                      dm_we
);

    // =========================================================================
    // Transfer FSM
    // =========================================================================
    typedef enum logic [2:0] {
        IDLE        = 3'd0,
        DM2L2_READ  = 3'd1,   // issuing devmem reads, writing prev read to L2
        DM2L2_WRITE = 3'd2,   // drain: write last devmem read to L2
        L22DM_READ  = 3'd3,   // issuing L2 reads, writing prev read to devmem
        L22DM_WRITE = 3'd4,   // drain: write last L2 read to devmem
        DONE        = 3'd5
    } xfer_state_t;

    xfer_state_t state;

    // Transfer parameter registers (latched on start)
    logic [15:0]               rd_count;
    logic [15:0]               wr_count;
    logic [15:0]               len_reg;
    logic [DM_ADDR_WIDTH-1:0]  dm_base_reg;
    logic [L2_ADDR_WIDTH-1:0]  l2_base_reg;
    logic                      source_is_tma; // 0=host, 1=TMA instruction

    // 1-cycle pipeline: rd_valid_d1 gates the write one cycle after the read
    logic                      rd_valid_d1;
    logic [L2_ADDR_WIDTH-1:0]  l2_wr_addr_d1;
    logic [DM_ADDR_WIDTH-1:0]  dm_wr_addr_d1;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state         <= IDLE;
            host_done     <= 1'b0;
            tma_done      <= 1'b0;
            rd_count      <= 16'd0;
            wr_count      <= 16'd0;
            len_reg       <= 16'd0;
            dm_base_reg   <= '0;
            l2_base_reg   <= '0;
            source_is_tma <= 1'b0;
            rd_valid_d1   <= 1'b0;
            l2_wr_addr_d1 <= '0;
            dm_wr_addr_d1 <= '0;
        end else begin
            // Pulsed outputs — deassert by default
            host_done   <= 1'b0;
            tma_done    <= 1'b0;
            rd_valid_d1 <= 1'b0;

            case (state)
                // ---- IDLE: wait for a request ----
                IDLE: begin
                    rd_count <= 16'd0;
                    wr_count <= 16'd0;
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

                // ---- DevMem → L2 ----
                DM2L2_READ: begin
                    // Issue devmem read at rd_count; pipeline L2 write for previous read
                    rd_valid_d1   <= 1'b1;
                    l2_wr_addr_d1 <= l2_base_reg + rd_count[L2_ADDR_WIDTH-1:0];
                    rd_count      <= rd_count + 16'd1;
                    if (rd_count + 1 >= len_reg)
                        state <= DM2L2_WRITE; // drain last read
                end

                DM2L2_WRITE: begin
                    // One more cycle to write the last devmem word to L2
                    state <= DONE;
                end

                // ---- L2 → DevMem ----
                L22DM_READ: begin
                    // Issue L2 read at rd_count; pipeline devmem write for previous read
                    rd_valid_d1   <= 1'b1;
                    dm_wr_addr_d1 <= dm_base_reg + rd_count[DM_ADDR_WIDTH-1:0];
                    rd_count      <= rd_count + 16'd1;
                    if (rd_count + 1 >= len_reg)
                        state <= L22DM_WRITE; // drain last read
                end

                L22DM_WRITE: begin
                    // One more cycle to write the last L2 word to devmem
                    state <= DONE;
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
                // Issue read to devmem at current rd_count
                dm_addr = dm_base_reg + rd_count[DM_ADDR_WIDTH-1:0];
                dm_en   = 1'b1;
                dm_we   = 1'b0;
                // Write previous devmem read result to L2 (1-cycle pipeline)
                if (rd_valid_d1) begin
                    sram_addr_b = l2_wr_addr_d1;
                    sram_din_b  = dm_dout;
                    sram_en_b   = 1'b1;
                    sram_we_b   = 1'b1;
                end
            end

            DM2L2_WRITE: begin
                // Drain: write last devmem read to L2
                sram_addr_b = l2_wr_addr_d1;
                sram_din_b  = dm_dout;
                sram_en_b   = 1'b1;
                sram_we_b   = 1'b1;
            end

            L22DM_READ: begin
                // Issue read to L2 SRAM at current rd_count
                sram_addr_b = l2_base_reg + rd_count[L2_ADDR_WIDTH-1:0];
                sram_en_b   = 1'b1;
                sram_we_b   = 1'b0;
                // Write previous L2 read result to devmem (1-cycle pipeline)
                if (rd_valid_d1) begin
                    dm_addr = dm_wr_addr_d1;
                    dm_din  = sram_dout_b;
                    dm_en   = 1'b1;
                    dm_we   = 1'b1;
                end
            end

            L22DM_WRITE: begin
                // Drain: write last L2 read to devmem
                dm_addr = dm_wr_addr_d1;
                dm_din  = sram_dout_b;
                dm_en   = 1'b1;
                dm_we   = 1'b1;
            end

            default: ;
        endcase
    end

endmodule
