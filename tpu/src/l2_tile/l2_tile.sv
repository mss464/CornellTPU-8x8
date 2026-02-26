`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// l2_tile.sv
//
// L2 shared SRAM tile. Sits between compute tiles and device memory.
// Contains a 32768×32-bit dual-port SRAM (blk_mem_gen_3) and a transfer FSM
// for DevMem↔L2 block copies.
//
// Port A: Compute tile side (L1↔L2 transfers, directly driven by compute_tile)
// Port B: Device memory side (DevMem↔L2 transfers, driven by internal FSM)
//
// Transfer FSM:
//   - DEVMEM_TO_L2: reads from devmem Port B, writes to L2 SRAM Port B
//   - L2_TO_DEVMEM: reads from L2 SRAM Port B, writes to devmem Port B
//   - Both are word-sequential burst copies with 1-cycle BRAM read latency
//
// L1↔L2 (Port A):
//   - Directly exposed as a memory port. The compute_tile drives this during
//     MODE=2 instructions. L2 tile does not arbitrate — Port A is always
//     available to the compute tile.
//////////////////////////////////////////////////////////////////////////////////

module l2_tile #(
    parameter L2_ADDR_WIDTH  = 15,   // 32768 words
    parameter DATA_WIDTH     = 32,
    parameter DM_ADDR_WIDTH  = 16    // device memory address width
)(
    input  logic                      clk,
    input  logic                      rst_n,

    // === Port A: Compute tile (L1↔L2) ===
    input  logic [L2_ADDR_WIDTH-1:0]  ct_addr_a,
    input  logic [DATA_WIDTH-1:0]     ct_din_a,
    output logic [DATA_WIDTH-1:0]     ct_dout_a,
    input  logic                      ct_en_a,
    input  logic                      ct_we_a,

    // === Port B: Device memory facing ===
    // L2 tile drives these to talk to device_mem Port B
    output logic [DM_ADDR_WIDTH-1:0]  dm_addr,
    output logic [DATA_WIDTH-1:0]     dm_din,
    input  logic [DATA_WIDTH-1:0]     dm_dout,
    output logic                      dm_en,
    output logic                      dm_we,

    // === Transfer control (from tpu.sv) ===
    input  logic                      start_dm_to_l2,   // pulse: start devmem→L2 copy
    input  logic                      start_l2_to_dm,   // pulse: start L2→devmem copy
    input  logic [DM_ADDR_WIDTH-1:0]  xfer_dm_base,     // devmem base address
    input  logic [L2_ADDR_WIDTH-1:0]  xfer_l2_base,     // L2 base address
    input  logic [15:0]               xfer_len,          // number of words to transfer
    output logic                      xfer_done          // asserted for 1 cycle when complete
);

    // =========================================================================
    // L2 SRAM — Port A = compute tile, Port B = internal (devmem transfers)
    // =========================================================================
    logic [L2_ADDR_WIDTH-1:0]  sram_addr_b;
    logic [DATA_WIDTH-1:0]     sram_din_b;
    logic [DATA_WIDTH-1:0]     sram_dout_b;
    logic                      sram_en_b;
    logic                      sram_we_b;

    blk_mem_gen_3 u_l2_sram (
        // Port A — Compute tile
        .clka(clk),
        .ena(ct_en_a),
        .wea(ct_we_a),
        .addra(ct_addr_a),
        .dina(ct_din_a),
        .douta(ct_dout_a),

        // Port B — DevMem transfer FSM
        .clkb(clk),
        .enb(sram_en_b),
        .web(sram_we_b),
        .addrb(sram_addr_b),
        .dinb(sram_din_b),
        .doutb(sram_dout_b)
    );

    // =========================================================================
    // DevMem↔L2 Transfer FSM
    // =========================================================================
    // Transfers are word-sequential. BRAM has 1-cycle read latency, so:
    //   Read phase:  assert addr+en → data valid next cycle
    //   Write phase: assert addr+din+en+we → written at posedge
    //
    // DEVMEM_TO_L2 (read devmem, write L2):
    //   Cycle N:   dm_addr=base+i, dm_en=1 (read request)
    //   Cycle N+1: dm_dout valid → sram_addr_b=base+i, sram_din_b=dm_dout, sram_we_b=1
    //
    // L2_TO_DEVMEM (read L2, write devmem):
    //   Cycle N:   sram_addr_b=base+i, sram_en_b=1 (read request)
    //   Cycle N+1: sram_dout_b valid → dm_addr=base+i, dm_din=sram_dout_b, dm_we=1

    typedef enum logic [2:0] {
        IDLE        = 3'd0,
        DM2L2_READ  = 3'd1,   // issuing devmem reads
        DM2L2_WRITE = 3'd2,   // writing to L2 SRAM (pipeline drain)
        L22DM_READ  = 3'd3,   // issuing L2 reads
        L22DM_WRITE = 3'd4,   // writing to devmem (pipeline drain)
        DONE        = 3'd5
    } xfer_state_t;

    xfer_state_t state;

    // Transfer counters
    logic [15:0] rd_count;    // number of reads issued
    logic [15:0] wr_count;    // number of writes completed
    logic [15:0] len_reg;
    logic [DM_ADDR_WIDTH-1:0] dm_base_reg;
    logic [L2_ADDR_WIDTH-1:0] l2_base_reg;

    // Pipeline: read data valid 1 cycle after read request
    logic        rd_valid_d1;
    logic [L2_ADDR_WIDTH-1:0] l2_wr_addr_d1;
    logic [DM_ADDR_WIDTH-1:0] dm_wr_addr_d1;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= IDLE;
            xfer_done   <= 1'b0;
            rd_count    <= 16'd0;
            wr_count    <= 16'd0;
            len_reg     <= 16'd0;
            dm_base_reg   <= 16'b0;
            l2_base_reg   <= 15'b0;
            rd_valid_d1   <= 1'b0;
            l2_wr_addr_d1 <= 15'b0;
            dm_wr_addr_d1 <= 16'b0;
        end else begin
            xfer_done   <= 1'b0;
            rd_valid_d1 <= 1'b0;

            case (state)
                IDLE: begin
                    rd_count <= 16'd0;
                    wr_count <= 16'd0;
                    if (start_dm_to_l2) begin
                        dm_base_reg <= xfer_dm_base;
                        l2_base_reg <= xfer_l2_base;
                        len_reg     <= xfer_len;
                        state       <= DM2L2_READ;
                    end else if (start_l2_to_dm) begin
                        dm_base_reg <= xfer_dm_base;
                        l2_base_reg <= xfer_l2_base;
                        len_reg     <= xfer_len;
                        state       <= L22DM_READ;
                    end
                end

                // ---- DevMem → L2 ----
                DM2L2_READ: begin
                    // Issue devmem read, pipeline L2 write
                    rd_valid_d1   <= 1'b1;
                    l2_wr_addr_d1 <= l2_base_reg + rd_count[L2_ADDR_WIDTH-1:0];
                    rd_count      <= rd_count + 16'd1;
                    if (rd_count + 1 >= len_reg) begin
                        state <= DM2L2_WRITE;  // drain last read
                    end
                end

                DM2L2_WRITE: begin
                    // One more cycle to write the last word
                    rd_valid_d1 <= 1'b0;
                    wr_count    <= wr_count + 16'd1;
                    state       <= DONE;
                end

                // ---- L2 → DevMem ----
                L22DM_READ: begin
                    rd_valid_d1   <= 1'b1;
                    dm_wr_addr_d1 <= dm_base_reg + rd_count[DM_ADDR_WIDTH-1:0];
                    rd_count      <= rd_count + 16'd1;
                    if (rd_count + 1 >= len_reg) begin
                        state <= L22DM_WRITE;
                    end
                end

                L22DM_WRITE: begin
                    rd_valid_d1 <= 1'b0;
                    wr_count    <= wr_count + 16'd1;
                    state       <= DONE;
                end

                DONE: begin
                    xfer_done <= 1'b1;
                    state     <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end

    // =========================================================================
    // Combinational output mux for Port B (SRAM) and DevMem signals
    // =========================================================================
    always_comb begin
        // Defaults — no activity
        sram_addr_b = 15'b0;
        sram_din_b  = 32'b0;
        sram_en_b   = 1'b0;
        sram_we_b   = 1'b0;
        dm_addr     = 16'b0;
        dm_din      = 32'b0;
        dm_en       = 1'b0;
        dm_we       = 1'b0;

        case (state)
            DM2L2_READ: begin
                // Issue read to devmem
                dm_addr = dm_base_reg + rd_count[DM_ADDR_WIDTH-1:0];
                dm_en   = 1'b1;
                dm_we   = 1'b0;
                // Write previous read result to L2 (pipelined)
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
                // Issue read to L2 SRAM
                sram_addr_b = l2_base_reg + rd_count[L2_ADDR_WIDTH-1:0];
                sram_en_b   = 1'b1;
                sram_we_b   = 1'b0;
                // Write previous L2 read result to devmem (pipelined)
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
