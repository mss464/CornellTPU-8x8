`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// l1.sv
//
// 8-Bank interleaved L1 Data Memory.
// Port A (32-bit): Multiplexed DMA access
// Port B (256-bit): Parallel access for Compute units
//////////////////////////////////////////////////////////////////////////////////

module l1 #(
    parameter DMA_ADDR_WIDTH = 13, // Addressing updated for 256-bit words
    parameter DMA_DATA_WIDTH = 256,
    parameter COMP_ADDR_WIDTH = 13,
    parameter COMP_DATA_WIDTH = 256
)(
    input  logic                     clk,
    input  logic                     rst_n,

    // Control interface 
    input  logic [15:0]              base_addr, // Kept for compatibility, but offset logic simplified

    // Write interface (from Slave Stream)
    input  logic                     dma_wr_en,
    input  logic [DMA_DATA_WIDTH-1:0] dma_wr_data,
    input  logic [15:0]              dma_write_pointer,

    // Read interface (to Master Stream)
    input  logic                     dma_rd_en,
    output logic [DMA_DATA_WIDTH-1:0] dma_rd_data,
    input  logic [15:0]              dma_read_pointer,

    // Compute-side BRAM port (Port B)
    input  logic [COMP_ADDR_WIDTH-1:0]    dma_comp_addr_b,
    input  logic [COMP_DATA_WIDTH-1:0]    dma_comp_din_b,
    output logic [COMP_DATA_WIDTH-1:0]    dma_comp_dout_b,
    input  logic                          dma_comp_en_b,
    input  logic                          dma_comp_we_b
);

    // Internal signals
    // Offset is now directly in 256-bit words
    wire [15:0] dma_addr;
    assign dma_addr = base_addr + (dma_wr_en ? dma_write_pointer : dma_read_pointer);

    wire [9:0] dma_bram_addr = dma_addr[9:0];

    //-----------------------------------------------
    // BRAM instantiation (true dual-port)
    //-----------------------------------------------
    genvar i;
    generate
        for (i = 0; i < 8; i = i + 1) begin : bank
            blk_mem_gen_0 u_bram (
                // Port A - DMA side (now aligned to 8x32 bits)
                .clka(clk),
                .ena(1'b1),
                .wea(dma_wr_en),
                .addra(dma_bram_addr),
                .dina(dma_wr_data[i*32 +: 32]),
                .douta(dma_rd_data[i*32 +: 32]),

                // Port B - Compute side
                .clkb(clk),
                .enb(dma_comp_en_b),
                .web(dma_comp_we_b),
                .addrb(dma_comp_addr_b),
                .dinb(dma_comp_din_b[i*32 +: 32]),
                .doutb(dma_comp_dout_b[i*32 +: 32])
            );
        end
    endgenerate

endmodule

