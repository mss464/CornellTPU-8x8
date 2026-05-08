`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// l2_tile.sv
//
// L2 shared SRAM tile. Sits between compute tiles and device memory.
// Contains a 32768×32-bit dual-port SRAM (blk_mem_gen_3) and a tma_engine
// for DevMem↔L2 block copies.
//
// Port A: Compute tile side (L1↔L2 transfers, directly driven by tpu.sv FSM)
// Port B: Device memory side (driven by internal tma_engine)
//
// Two transfer request sources (routed to tma_engine):
//   - Host-controlled (modes 5/6): start_dm_to_l2 / start_l2_to_dm from tpu.sv
//   - TMA instruction: tma_req pulse from tensorcore (via tpu.sv)
//
// xfer_done: 1-cycle pulse when a host-controlled transfer finishes
// tma_done:  1-cycle pulse when a TMA-instruction transfer finishes
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
    // l2_tile drives these to talk to device_mem Port B (via tma_engine)
    output logic [DM_ADDR_WIDTH-1:0]  dm_addr,
    output logic [DATA_WIDTH-1:0]     dm_din,
    input  logic [DATA_WIDTH-1:0]     dm_dout,
    output logic                      dm_en,
    output logic                      dm_we,
    input  logic                      dm_ready,
    input  logic                      dm_rvalid,
    input  logic                      dm_bvalid,

    // === Host-controlled transfer (from tpu.sv, modes 5/6) ===
    input  logic                      start_dm_to_l2,
    input  logic                      start_l2_to_dm,
    input  logic [DM_ADDR_WIDTH-1:0]  xfer_dm_base,
    input  logic [L2_ADDR_WIDTH-1:0]  xfer_l2_base,
    input  logic [15:0]               xfer_len,
    output logic                      xfer_done,     // host transfer complete

    // === TMA instruction port (from tensorcore via tpu.sv) ===
    input  logic                      tma_req,       // 1-cycle pulse: start TMA
    input  logic                      tma_dir,       // 0=DM_TO_L2, 1=L2_TO_DM
    input  logic [DM_ADDR_WIDTH-1:0]  tma_dm_base,
    input  logic [L2_ADDR_WIDTH-1:0]  tma_l2_base,
    input  logic [15:0]               tma_len,
    output logic                      tma_done       // TMA transfer complete
);

    // =========================================================================
    // L2 SRAM — Port A = compute tile, Port B = tma_engine
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

        // Port B — TMA engine
        .clkb(clk),
        .enb(sram_en_b),
        .web(sram_we_b),
        .addrb(sram_addr_b),
        .dinb(sram_din_b),
        .doutb(sram_dout_b)
    );

    // =========================================================================
    // TMA Engine — handles both host-controlled and TMA-instruction transfers
    // =========================================================================
    tma_engine #(
        .L2_ADDR_WIDTH(L2_ADDR_WIDTH),
        .DATA_WIDTH(DATA_WIDTH),
        .DM_ADDR_WIDTH(DM_ADDR_WIDTH)
    ) u_tma_engine (
        .clk(clk),
        .rst_n(rst_n),

        // Host-controlled (modes 5/6)
        .start_dm_to_l2(start_dm_to_l2),
        .start_l2_to_dm(start_l2_to_dm),
        .host_dm_base(xfer_dm_base),
        .host_l2_base(xfer_l2_base),
        .host_len(xfer_len),
        .host_done(xfer_done),

        // TMA instruction
        .tma_req(tma_req),
        .tma_dir(tma_dir),
        .tma_dm_base(tma_dm_base),
        .tma_l2_base(tma_l2_base),
        .tma_len(tma_len),
        .tma_done(tma_done),

        // L2 SRAM Port B
        .sram_addr_b(sram_addr_b),
        .sram_din_b(sram_din_b),
        .sram_dout_b(sram_dout_b),
        .sram_en_b(sram_en_b),
        .sram_we_b(sram_we_b),

        // DevMem Port B
        .dm_addr(dm_addr),
        .dm_din(dm_din),
        .dm_dout(dm_dout),
        .dm_en(dm_en),
        .dm_we(dm_we),
        .dm_ready(dm_ready),
        .dm_rvalid(dm_rvalid),
        .dm_bvalid(dm_bvalid)
    );

endmodule
