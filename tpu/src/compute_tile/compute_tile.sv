`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Module Name: compute_tile
// Description: Wrapper for tensorcore (logic) and l1 (data memory).
//              Exposes TMA signals so tpu.sv can wire them to l2_tile.
//////////////////////////////////////////////////////////////////////////////////

module compute_tile #(
    parameter N = 4,
    parameter ADDR_WIDTH = 13,
    parameter DATA_WIDTH = 32,
    parameter COMP_DATA_WIDTH = 256,
    parameter DMA_ADDR_WIDTH = 13,
    parameter DMA_DATA_WIDTH = 256,
    parameter COMP_ADDR_WIDTH = 13,
    parameter MEM_LATENCY = 2
)(
    input  logic clk,
    input  logic rst_n,

    // High-level control
    input  logic start,
    output logic done,

    // DMA Instruction Interface
    input  logic        instr_write_en,
    input  logic [7:0]  iram_addr,
    input  logic [63:0] dma_iram_din,

    // DMA Data Interface
    input  logic [15:0]           base_addr,
    input  logic                  dma_wr_en,
    input  logic [DATA_WIDTH-1:0] dma_wr_data,
    input  logic [15:0]           dma_write_pointer,
    input  logic                  dma_rd_en,
    output logic [DATA_WIDTH-1:0] dma_rd_data,
    input  logic [15:0]           dma_read_pointer,

    // TMA signals (tensorcore → l2_tile via tpu.sv)
    output logic        tma_req,
    output logic        tma_dir,
    output logic [15:0] tma_dm_base,
    output logic [14:0] tma_l2_base,
    output logic [15:0] tma_len,
    input  logic        tma_done
);

    // Internal BRAM connection
    logic [ADDR_WIDTH-1:0] pc_addr_b;
    logic [COMP_DATA_WIDTH-1:0] pc_din_b;
    logic [COMP_DATA_WIDTH-1:0] pc_dout_b;
    logic                  pc_en_b;
    logic                  pc_we_b;

    // Instantiate TensorCore
    tensorcore #(
        .ADDR_WIDTH(ADDR_WIDTH),
        .DATA_WIDTH(DATA_WIDTH),
        .COMP_DATA_WIDTH(COMP_DATA_WIDTH),
        .N(N),
        .MEM_LATENCY(MEM_LATENCY)
    ) u_tensorcore (
        .clk(clk),
        .rst_n(rst_n),
        .start(start),
        .done(done),
        .instr_write_en(instr_write_en),
        .iram_addr(iram_addr),
        .dma_iram_din(dma_iram_din),
        .bram_addr_b(pc_addr_b),
        .bram_din_b(pc_din_b),
        .bram_dout_b(pc_dout_b),
        .bram_en_b(pc_en_b),
        .bram_we_b(pc_we_b),
        .tma_req(tma_req),
        .tma_dir(tma_dir),
        .tma_dm_base(tma_dm_base),
        .tma_l2_base(tma_l2_base),
        .tma_len(tma_len),
        .tma_done(tma_done)
    );

    // Instantiate L1
    l1 #(
        .COMP_ADDR_WIDTH(COMP_ADDR_WIDTH),
        .COMP_DATA_WIDTH(COMP_DATA_WIDTH),
        .DMA_ADDR_WIDTH(DMA_ADDR_WIDTH),
        .DMA_DATA_WIDTH(DMA_DATA_WIDTH)
    ) u_l1 (
        .clk(clk),
        .rst_n(rst_n),
        .base_addr(base_addr),
        .dma_wr_en(dma_wr_en),
        .dma_wr_data(dma_wr_data),
        .dma_write_pointer(dma_write_pointer),
        .dma_rd_en(dma_rd_en),
        .dma_rd_data(dma_rd_data),
        .dma_read_pointer(dma_read_pointer),
        .dma_comp_addr_b(pc_addr_b),
        .dma_comp_din_b(pc_din_b),
        .dma_comp_dout_b(pc_dout_b),
        .dma_comp_en_b(pc_en_b),
        .dma_comp_we_b(pc_we_b)
    );

endmodule
