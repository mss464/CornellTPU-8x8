`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// device_mem.sv
//
// 8-Bank interleaved Device Memory.
// Port A: Multiplexed Host DMA
// Port B: Multiplexed L2 tile connectivity
//////////////////////////////////////////////////////////////////////////////////

module device_mem #(
    parameter ADDR_WIDTH = 19,
    parameter DATA_WIDTH = 256
)(
    input  logic                     clk,
    input  logic                     rst_n,

    // Control interface
    input  logic [ADDR_WIDTH-1:0]    base_addr,

    // Write interface — Port A (from Slave Stream)
    input  logic                     dma_wr_en,
    input  logic [DATA_WIDTH-1:0]    dma_wr_data,
    input  logic [18:0]              dma_write_pointer,

    // Read interface — Port A (to Master Stream)
    input  logic                     dma_rd_en,
    output logic [DATA_WIDTH-1:0]    dma_rd_data,
    input  logic [18:0]              dma_read_pointer,

    // L2 tile port — Port B (remains 32-bit for now)
    input  logic [ADDR_WIDTH-1:0]    l2_addr_b,
    input  logic [31:0]              l2_din_b,
    output logic [31:0]              l2_dout_b,
    input  logic                     l2_en_b,
    input  logic                     l2_we_b
);

    // Address generation: base + offset
    wire [ADDR_WIDTH-1:0] dma_addr;
    assign dma_addr = base_addr + (dma_wr_en ? dma_write_pointer : dma_read_pointer);

    wire [15:0] dma_bram_addr = dma_addr[15:0];
    
    wire [2:0] l2_bank_sel = l2_addr_b[2:0];
    wire [15:0] l2_bram_addr = l2_addr_b[18:3];

    wire [31:0] l2_dout_b_arr [8];

    reg [2:0] l2_bank_sel_q;
    always_ff @(posedge clk) begin
        l2_bank_sel_q <= l2_bank_sel;
    end
    assign l2_dout_b = l2_dout_b_arr[l2_bank_sel_q];

    //-----------------------------------------------
    // BRAM instantiation (true dual-port)
    //-----------------------------------------------
    genvar i;
    generate
        for (i = 0; i < 8; i = i + 1) begin : bank
            blk_mem_gen_2 u_bram (
                // Port A — Host DMA (256-bit total across 8 banks)
                .clka(clk),
                .ena(1'b1),
                .wea(dma_wr_en),
                .addra(dma_bram_addr),
                .dina(dma_wr_data[i*32 +: 32]),
                .douta(dma_rd_data[i*32 +: 32]),

                // Port B — L2 tile (stub)
                .clkb(clk),
                .enb(l2_en_b),
                .web(l2_we_b && (l2_bank_sel == i)),
                .addrb(l2_bram_addr),
                .dinb(l2_din_b),
                .doutb(l2_dout_b_arr[i])
            );
        end
    endgenerate

endmodule

