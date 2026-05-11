`timescale 1ns / 1ps
////////////////////////////////////////////////////////////////////////////////
// Module Name: compute_core
// Description: Orchestrates VPU, Systolic Array, and Vector Add units.
//              Intefaces with a banked BRAM (Wide Memory).
////////////////////////////////////////////////////////////////////////////////

module compute_core #(
    parameter ADDR_WIDTH = 13,
    parameter DATA_WIDTH = 32,
    parameter NUM_BANKS  = 8,

    // VPU-specific params
    parameter VPU_DATA_W  = 32,
    parameter VPU_ADDR_W  = 13,
    parameter VPU_OP_W    = 4,
    parameter VPU_IADDR_W = 5
)(
    input  logic clk,
    input  logic rst_n,
    input logic [1:0] mode_compute,
    input  logic [ADDR_WIDTH-1:0]    addr_a_compute,
    input  logic [ADDR_WIDTH-1:0]    addr_b_compute,
    input  logic [ADDR_WIDTH-1:0]    addr_out_compute,
    input logic [ADDR_WIDTH-1:0]     addr_const_compute,
    input logic [9:0] opcode_compute,
    input  logic [22:0]              len_compute,
    input logic start_systolic_compute,
    input logic start_vadd_compute,
    input logic start_vpu_compute,
    output logic systolic_done_compute,
    output logic vadd_done_compute,
    output logic vpu_done_compute,

    // VPU SIMD fields
    input logic [2:0] vpu_type_compute,
    input logic [2:0] vreg_dst_compute,
    input logic [2:0] vreg_a_compute,
    input logic [2:0] vreg_b_compute,
    input logic [2:0] vpu_opcode_compute,
    input logic scalar_b_compute,

    // BRAM Port B Interface (Wide)
    output logic [ADDR_WIDTH-1:0]            bram_addr_b,
    output logic [NUM_BANKS*DATA_WIDTH-1:0]  bram_din_b,
    input  logic [NUM_BANKS*DATA_WIDTH-1:0]  bram_dout_b,
    output logic                             bram_en_b,
    output logic [NUM_BANKS-1:0]             bram_we_b
);

    //-------------------------------------------------------------------------
    // Bank-parallel Vector Add
    //-------------------------------------------------------------------------
    logic [ADDR_WIDTH-1:0]            vadd_addr_wide;
    logic [NUM_BANKS*DATA_WIDTH-1:0]  vadd_din_wide;
    logic [NUM_BANKS*DATA_WIDTH-1:0]  vadd_dout_wide;
    logic                             vadd_en_wide;
    logic [NUM_BANKS-1:0]             vadd_we_wide;
    dummy_unit #(
        .ADDR_WIDTH(ADDR_WIDTH),
        .DATA_WIDTH(DATA_WIDTH),
        .NUM_BANKS (NUM_BANKS)
    ) u_dummy_unit (
        .clk(clk),
        .rst_n(rst_n),
        .start(start_vadd_compute),
        .done(vadd_done_compute),

        // BRAM B port (wide banked view)
        .bram_addr_b(vadd_addr_wide),
        .bram_din_b (vadd_din_wide),
        .bram_dout_b(vadd_dout_wide),
        .bram_en_b  (vadd_en_wide),
        .bram_we_b  (vadd_we_wide),

        .addr_a_vadd(addr_a_compute),
        .addr_b_vadd(addr_b_compute),
        .addr_out_vadd(addr_out_compute),
        .len_vadd(len_compute)
    );

    //-------------------------------------------------------------------------
    // Systolic Array (MXU) - Wide Interface
    //-------------------------------------------------------------------------
    logic [ADDR_WIDTH-1:0]            systolic_addr;
    logic [NUM_BANKS*DATA_WIDTH-1:0]  systolic_din_b;
    logic [NUM_BANKS*DATA_WIDTH-1:0]  systolic_dout_b;
    logic                             systolic_en_b;
    logic                             systolic_we_b;
    
    // MXU produces a single WE bit, we need to expand it to all banks?
    // MXU logic: `output logic mem_write_en` (1 bit)
    // If MXU writes, it writes a full row (all banks).
    // So we expand systolic_we_b (1 bit) to systolic_we_wide (8 bits).
    
    logic [NUM_BANKS-1:0] systolic_we_wide;
    assign systolic_we_wide = systolic_we_b ? {NUM_BANKS{1'b1}} : '0;

    mxu #(
        .N(4),
        .DATA_WIDTH(DATA_WIDTH),
        .BANKING_FACTOR(NUM_BANKS), // Use 8 banks!
        .ADDRESS_WIDTH(ADDR_WIDTH),
        .MEM_LATENCY(3)
    ) u_mxu (
        .clk(clk),
        .rst_n(rst_n),

        .start(start_systolic_compute),
        .done(systolic_done_compute),

        .base_addr_w(addr_a_compute),
        .base_addr_x(addr_b_compute),
        .base_addr_out(addr_out_compute),
        
        // BRAM port
        .mem_req_addr(systolic_addr),
        .mem_req_data(systolic_din_b),
        .mem_resp_data(systolic_dout_b),
        .mem_read_en (systolic_en_b),
        .mem_write_en(systolic_we_b)
    );

    //-------------------------------------------------------------------------
    // VPU SIMD - Wide Interface
    //-------------------------------------------------------------------------
    logic [ADDR_WIDTH-1:0]            vpu_addr;
    logic [NUM_BANKS*DATA_WIDTH-1:0]  vpu_din_b;
    logic [NUM_BANKS*DATA_WIDTH-1:0]  vpu_dout_b;
    logic                             vpu_en_b;
    logic [NUM_BANKS-1:0]             vpu_we_b; // VPU SIMD produces 8-bit WE?

    // Check vpu_simd interface. We will update it to produce per-lane WE?
    // Or just 1 bit if it stores vector?
    // It's safer if VPU SIMD produces mask, but typically VSTORE stores all 8.
    // Let's assume vpu_simd.sv will output 1-bit WE and we expand, OR output 8-bit WE.
    // Given vector masking is a thing, 8-bit WE is better.
    // I will update vpu_simd to output logic [NUM_LANES-1:0] bram_we.

    vpu_simd #(
        .DATA_W(VPU_DATA_W),
        .ADDR_W(VPU_ADDR_W),
        .NUM_LANES(NUM_BANKS)
    ) u_vpu_simd (
        .clk(clk),
        .rst_n(rst_n),
        .start(start_vpu_compute),

        // Instruction fields
        .addr_a(addr_a_compute),
        .addr_b(addr_b_compute),
        .addr_out(addr_out_compute),
        .opcode(opcode_compute),
        .addr_const(addr_const_compute),
        .vpu_type(vpu_type_compute),
        .vreg_dst(vreg_dst_compute),
        .vreg_a(vreg_a_compute),
        .vreg_b(vreg_b_compute),
        .vpu_opcode(vpu_opcode_compute),
        .scalar_b(scalar_b_compute),

        // BRAM B port
        .bram_addr(vpu_addr),
        .bram_din(vpu_din_b),
        .bram_dout(vpu_dout_b),
        .bram_en(vpu_en_b),
        .bram_we(vpu_we_b),
        .done(vpu_done_compute)
    );
    
    //---------------------------------------------
    // BRAM PORT B ARBITRATION
    //---------------------------------------------
    always_comb begin
        // default safe values
        bram_addr_b = '0;
        bram_din_b  = '0;
        bram_en_b   = 1'b0;
        bram_we_b   = '0;

        // Feed read data to the wide-port compute units.
        vadd_dout_wide  = bram_dout_b;
        systolic_dout_b  = bram_dout_b;
        vpu_dout_b       = bram_dout_b;

        case (mode_compute)
            
            2'b00: begin  // VPU
                bram_addr_b = vpu_addr;
                bram_din_b  = vpu_din_b;
                bram_en_b   = vpu_en_b;
                bram_we_b   = vpu_we_b;
            end

            2'b01: begin  // Systolic
                bram_addr_b = systolic_addr;
                bram_din_b  = systolic_din_b;
                bram_en_b   = systolic_en_b;
                bram_we_b   = systolic_we_wide;
            end

            2'b10: begin  // Vadd
                bram_addr_b = vadd_addr_wide;
                bram_din_b  = vadd_din_wide;
                bram_en_b   = vadd_en_wide;
                bram_we_b   = vadd_we_wide;
            end

            default: begin
                // No-op
            end
        endcase
    end

endmodule
