`timescale 1ns / 1ps
////////////////////////////////////////////////////////////////////////////////
// scratchpad.sv - Dual-port scratchpad memory with 8-way banking
//
// Description:
//   - Banks: 8 x (DEPTH x 32-bit)
//   - Port A (DMA): 32-bit interface, accesses individual banks based on addr[2:0]
//   - Port B (Compute): 256-bit interface, accesses all 8 banks in parallel
////////////////////////////////////////////////////////////////////////////////

module scratchpad #(
    parameter ADDR_WIDTH = 13,
    parameter DATA_WIDTH = 32,
    parameter NUM_BANKS  = 8
)(
    input  logic                     clk,
    input  logic                     rst_n,

    // Control interface
    input  logic [ADDR_WIDTH-1:0]    base_addr,

    // Write interface (from Slave Stream)
    input  logic dma_wr_en,
    input  logic [DATA_WIDTH-1:0]    dma_wr_data,
    input  logic [15:0]              dma_write_pointer,

    // Read interface (to Master Stream)
    input  logic dma_rd_en,
    output logic [DATA_WIDTH-1:0]    dma_rd_data,
    input  logic [15:0]              dma_read_pointer,

    // Compute-side BRAM port (Port B) - WIDE INTERFACE
    // Address addresses a ROW of 8 words.
    // Address input should be the byte/word address? 
    // We expect the LSBs to be ignored for row selection, but passed for validity if needed.
    // For simplicity, we use dma_comp_addr_b[ADDR_WIDTH-1:3] for row index.
    input  logic [ADDR_WIDTH-1:0]            dma_comp_addr_b,
    input  logic [NUM_BANKS*DATA_WIDTH-1:0]  dma_comp_din_b,
    output logic [NUM_BANKS*DATA_WIDTH-1:0]  dma_comp_dout_b,
    input  logic                             dma_comp_en_b,
    input  logic [NUM_BANKS-1:0]             dma_comp_we_b
);

    // Internal signals
    logic [ADDR_WIDTH-1:0] dma_addr;
    
    // Combinational address calculation (DMA Logic)
    // base_addr is the start of the current segment in the scratchpad.
    // dma_write_pointer/dma_read_pointer are the offsets within that segment.
    assign dma_addr = base_addr + (dma_wr_en ? dma_write_pointer : dma_read_pointer);

    // DMA Banking Logic
    // Bank select = dma_addr[2:0]
    // Row address = dma_addr >> 3

    logic [2:0] dma_bank_sel;
    logic [ADDR_WIDTH-4:0] dma_row_addr; // ADDR_WIDTH=13 -> [12:0]. row addr is [12:3] -> 10 bits.
    logic [ADDR_WIDTH-4:0] comp_row_addr;

    assign dma_bank_sel = dma_addr[2:0];
    assign dma_row_addr = dma_addr[ADDR_WIDTH-1:3];
    assign comp_row_addr = dma_comp_addr_b[ADDR_WIDTH-1:3];

    // Pipeline bank select for read return (mem_wrapper has 1 cycle latency)
    logic [2:0] dma_bank_sel_q;
    always_ff @(posedge clk) begin
        if (dma_rd_en) begin
            dma_bank_sel_q <= dma_bank_sel;
        end
    end

    // Bank connections
    logic [DATA_WIDTH-1:0] bank_dout_a [NUM_BANKS-1:0];

    genvar i;
    generate
        for (i = 0; i < NUM_BANKS; i++) begin : BANKS
            logic bank_ena;
            logic bank_wea;
            
            // Activate bank if DMA is enabled AND this bank is selected
            assign bank_ena = (dma_wr_en || dma_rd_en) && (dma_bank_sel == i[2:0]);
            assign bank_wea = dma_wr_en && (dma_bank_sel == i[2:0]);

            mem_wrapper #(
                .DATA_WIDTH(DATA_WIDTH),
                .ADDR_WIDTH(ADDR_WIDTH-3) // 10 bits depth (1024 words per bank)
            ) u_bank (
                // Port A - DMA (Single word access)
                .clka(clk),
                .ena(bank_ena),
                .wea(bank_wea),
                .addra(dma_row_addr), // Address within bank
                .dina(dma_wr_data),
                .douta(bank_dout_a[i]),

                // Port B - Compute (Parallel vector access)
                .clkb(clk),
                .enb(dma_comp_en_b), // Global enable
                .web(dma_comp_we_b[i]),   // Per-bank write enable
                .addrb(comp_row_addr),
                .dinb(dma_comp_din_b[(i*DATA_WIDTH) +: DATA_WIDTH]),
                .doutb(dma_comp_dout_b[(i*DATA_WIDTH) +: DATA_WIDTH])
            );
        end
    endgenerate

    // Mux for DMA read data
    // Since mem_wrapper registers output, we just mux the outputs
    assign dma_rd_data = bank_dout_a[dma_bank_sel_q];

endmodule
