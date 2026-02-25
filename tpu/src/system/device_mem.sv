`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// device_mem.sv
//
// Device memory module. Instantiates a 65536×32-bit dual-port BRAM (blk_mem_gen_2)
// with base-plus-offset addressing on Port A (host DMA) and a stub Port B for
// future L2 tile connectivity.
//
// Port A: Host DMA path (modes 1/2 in tpu.sv)
// Port B: Reserved for L2 tile (P1.2)
//////////////////////////////////////////////////////////////////////////////////

module device_mem #(
    parameter ADDR_WIDTH = 16,
    parameter DATA_WIDTH = 32
)(
    input  logic                     clk,
    input  logic                     rst_n,

    // Control interface
    input  logic [ADDR_WIDTH-1:0]    base_addr,

    // Write interface — Port A (from Slave Stream)
    input  logic                     dma_wr_en,
    input  logic [DATA_WIDTH-1:0]    dma_wr_data,
    input  logic [15:0]              dma_write_pointer,

    // Read interface — Port A (to Master Stream)
    input  logic                     dma_rd_en,
    output logic [DATA_WIDTH-1:0]    dma_rd_data,
    input  logic [15:0]              dma_read_pointer,

    // L2 tile port — Port B (stub, active in P1.2)
    input  logic [ADDR_WIDTH-1:0]    l2_addr_b,
    input  logic [DATA_WIDTH-1:0]    l2_din_b,
    output logic [DATA_WIDTH-1:0]    l2_dout_b,
    input  logic                     l2_en_b,
    input  logic                     l2_we_b
);

    // Address generation: base + offset
    wire [ADDR_WIDTH-1:0] dma_addr;
    assign dma_addr = base_addr + (dma_wr_en ? dma_write_pointer[ADDR_WIDTH-1:0] : dma_read_pointer[ADDR_WIDTH-1:0]);

    //-----------------------------------------------
    // BRAM instantiation (true dual-port)
    //-----------------------------------------------
    blk_mem_gen_2 u_bram (
        // Port A — Host DMA
        .clka(clk),
        .ena(1'b1),
        .wea(dma_wr_en),
        .addra(dma_addr),
        .dina(dma_wr_data),
        .douta(dma_rd_data),

        // Port B — L2 tile (stub)
        .clkb(clk),
        .enb(l2_en_b),
        .web(l2_we_b),
        .addrb(l2_addr_b),
        .dinb(l2_din_b),
        .doutb(l2_dout_b)
    );

endmodule
