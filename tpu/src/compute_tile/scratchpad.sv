`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// scratchpad.sv
//
// scratchpad is the top-level memory module that instantiates a true dual-port 
// BRAM and manages address generation for DMA-side and compute-side accesses. 
// The memory subsystem provides a clean interface between external memory 
// transfers and accelerator compute.
//
// Interface
// ---------
//
// Parameters:
// - ADDR_WIDTH: The size in bits of the BRAM address space.
// - DATA_WIDTH: The size in bits of each BRAM data element.
//
// Control Signals:
// - clk: Clock signal
// - rst_n: Active-low reset signal
//
// To/from DMA / Memory (Port A):
// Used for loading data from external memory into BRAM and storing results 
// back to memory.
// - base_addr [ADDR_WIDTH-1:0]: Base address in BRAM for the current buffer.
// - dma_wr_en: Write enable. Asserted when DMA write data is valid.
// - dma_wr_data [DATA_WIDTH-1:0]: Data to be written into BRAM.
// - dma_write_pointer [15:0]: Offset from base_addr for DMA writes.
// - dma_rd_en: Read enable. Asserted when DMA requests data.
// - dma_rd_data [DATA_WIDTH-1:0]: Data read from BRAM.
// - dma_read_pointer [15:0]: Offset from base_addr for DMA reads.
//
// All DMA accesses use base-plus-offset addressing:
//   bram_addr = base_addr + pointer
//
// To/from Compute (Port B):
// Used by compute units such as systolic array.
// - dma_comp_addr_b [ADDR_WIDTH-1:0]: BRAM address for compute access
// - dma_comp_din_b [DATA_WIDTH-1:0]: Data written by compute
// - dma_comp_dout_b [DATA_WIDTH-1:0]: Data read by compute
// - dma_comp_en_b: Compute-side BRAM enable
// - dma_comp_we_b: Compute-side write enable
// 
// Port B provides single-cycle, random-access reads and writes and operates 
// independently of DMA traffic.
//////////////////////////////////////////////////////////////////////////////////

module scratchpad #(
    parameter ADDR_WIDTH = 13,
    parameter DATA_WIDTH = 32
)(
    input  logic                     clk,
    input  logic                     rst_n,

    // Control interface
    input  logic [ADDR_WIDTH-1:0]    base_addr,

    // Write interface (from Slave Stream)
    input  logic dma_wr_en,
    input  logic [DATA_WIDTH-1:0] dma_wr_data,
    input logic [15:0] dma_write_pointer,

    // Read interface (to Master Stream)
    input  logic dma_rd_en,
    output logic [DATA_WIDTH-1:0] dma_rd_data,
    input logic [15:0] dma_read_pointer,

    // Compute-side BRAM port (Port B)
    input  logic [ADDR_WIDTH-1:0]    dma_comp_addr_b,
    input  logic [DATA_WIDTH-1:0]    dma_comp_din_b,
    output logic [DATA_WIDTH-1:0]    dma_comp_dout_b,
    input  logic                     dma_comp_en_b,
    input  logic                     dma_comp_we_b
);

    // Internal signals
    wire [ADDR_WIDTH-1:0] dma_addr;
    assign dma_addr = base_addr + (dma_wr_en ? dma_write_pointer[ADDR_WIDTH-1:0] : dma_read_pointer[ADDR_WIDTH-1:0]);


    //-----------------------------------------------
    // BRAM instantiation (true dual-port)
    //-----------------------------------------------
    // Xilinx Block RAM IP
    blk_mem_gen_0 u_bram (
        // Port A - DMA side (FSM-controlled)
        .clka(clk),
        .ena(1'b1),
        .wea(dma_wr_en),
        .addra(dma_addr),
        .dina(dma_wr_data),
        .douta(dma_rd_data),

        // Port B - Compute side
        .clkb(clk),
        .enb(1'b1),
        .web(dma_comp_we_b),
        .addrb(dma_comp_addr_b),
        .dinb(dma_comp_din_b),
        .doutb(dma_comp_dout_b)
    );

endmodule
