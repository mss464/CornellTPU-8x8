`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 11/21/2025 05:41:52 PM
// Design Name: 
// Module Name: decoder
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////


module decoder(
    input logic [63:0] instr_decode,
    output logic [22:0] len_decode,
    output logic [12:0] addr_out_decode,
    output logic [12:0] addr_b_decode,
    output logic [12:0] addr_a_decode,
    output logic [1:0] mode_decode,

    // VPU SIMD fields
    output logic [2:0] vpu_type_decode,
    output logic [2:0] vreg_dst_decode,
    output logic [2:0] vreg_a_decode,
    output logic [2:0] vreg_b_decode,
    output logic [2:0] vpu_opcode_decode,
    output logic scalar_b_decode
    );

    assign len_decode = instr_decode[22:0];
    assign addr_out_decode = instr_decode[35:23];
    assign addr_b_decode = instr_decode[48:36];
    assign addr_a_decode = instr_decode[61:49];
    assign mode_decode = instr_decode[63:62];

    // VPU SIMD instruction decoding
    assign vpu_type_decode = instr_decode[22:20];
    assign vreg_dst_decode = instr_decode[19:17];
    assign vreg_a_decode = instr_decode[16:14];
    assign vreg_b_decode = instr_decode[13:11];
    assign vpu_opcode_decode = instr_decode[6:4];
    assign scalar_b_decode = instr_decode[3];

endmodule
