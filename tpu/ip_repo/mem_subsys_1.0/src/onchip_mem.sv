`timescale 1ns / 1ps
// ============================================================================
// onchip_mem.sv — On-Chip Memory (SRAM tile)
//
// Single dual-port BRAM (32-bit × 32768 words = 128 KB).
//   Port A: Driven by mem_ctrl for sys_mem ↔ on-chip transfers
//   Port B: Reserved for future compute tile connection (active low enable)
//
// Uses blk_mem_gen_3 (Xilinx Block RAM Generator).
// ============================================================================

module onchip_mem #(
    parameter ADDR_WIDTH = 15,   // 32768 words
    parameter DATA_WIDTH = 32
)(
    input  logic clk,
    input  logic rst_n,

    // ── Port A: System memory transfer side (mem_ctrl) ──────────────
    input  logic [ADDR_WIDTH-1:0]  addr_a,
    input  logic [DATA_WIDTH-1:0]  din_a,
    output logic [DATA_WIDTH-1:0]  dout_a,
    input  logic                   en_a,
    input  logic                   we_a,

    // ── Port B: Compute tile side (reserved, active low) ────────────
    input  logic [ADDR_WIDTH-1:0]  addr_b,
    input  logic [DATA_WIDTH-1:0]  din_b,
    output logic [DATA_WIDTH-1:0]  dout_b,
    input  logic                   en_b,
    input  logic                   we_b
);

    blk_mem_gen_3 u_onchip_sram (
        // Port A — mem_ctrl side
        .clka  (clk),
        .ena   (en_a),
        .wea   (we_a),
        .addra (addr_a),
        .dina  (din_a),
        .douta (dout_a),

        // Port B — compute tile side (stub for now)
        .clkb  (clk),
        .enb   (en_b),
        .web   (we_b),
        .addrb (addr_b),
        .dinb  (din_b),
        .doutb (dout_b)
    );

endmodule
