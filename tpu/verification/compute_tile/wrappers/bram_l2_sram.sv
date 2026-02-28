`timescale 1ns / 1ps

// Behavioral model for blk_mem_gen_3 (L2 Shared SRAM)
// 32768×32-bit dual-port SRAM, 15-bit address, 1-cycle registered output latency.
// Matches Xilinx Block RAM IP: 1-cycle registered output latency.
module blk_mem_gen_3 (
    input clka,
    input ena,
    input [0:0] wea,
    input [14:0] addra,
    input [31:0] dina,
    output reg [31:0] douta,
    input clkb,
    input enb,
    input [0:0] web,
    input [14:0] addrb,
    input [31:0] dinb,
    output reg [31:0] doutb
);
    reg [31:0] mem [0:32767];
    integer i;
    initial begin
        for (i = 0; i < 32768; i = i + 1) mem[i] = 0;
    end

    // 1-cycle read latency (matches Xilinx BRAM IP)
    always @(posedge clka) begin
        if (ena) begin
            if (wea) mem[addra] <= dina;
            douta <= mem[addra];
        end
    end

    always @(posedge clkb) begin
        if (enb) begin
            if (web) mem[addrb] <= dinb;
            doutb <= mem[addrb];
        end
    end
endmodule
