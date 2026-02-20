`timescale 1ns / 1ps

// Behavioral model for blk_mem_gen_0 (Data BRAM)
module blk_mem_gen_0 (
    input clka,
    input ena,
    input [0:0] wea,
    input [12:0] addra,
    input [31:0] dina,
    output reg [31:0] douta,
    input clkb,
    input enb,
    input [0:0] web,
    input [12:0] addrb,
    input [31:0] dinb,
    output reg [31:0] doutb
);
    reg [31:0] mem [0:8191];
    reg [31:0] q1_a, q2_a;
    reg [31:0] q1_b, q2_b;
    integer i;
    initial begin
        for (i = 0; i < 8192; i = i + 1) mem[i] = 0;
    end

    always @(posedge clka) begin
        if (ena) begin
            if (wea) mem[addra] <= dina;
            q1_a <= mem[addra];
        end
        q2_a <= q1_a;
        douta <= q2_a;
    end

    always @(posedge clkb) begin
        if (enb) begin
            if (web) mem[addrb] <= dinb;
            q1_b <= mem[addrb];
        end
        q2_b <= q1_b;
        doutb <= q2_b;
    end
endmodule

// Behavioral model for blk_mem_gen_1 (Instruction BRAM)
module blk_mem_gen_1 (
    input clka,
    input ena,
    input [0:0] wea,
    input [7:0] addra,
    input [63:0] dina,
    output reg [63:0] douta,
    input clkb,
    input enb,
    input [0:0] web,
    input [7:0] addrb,
    input [63:0] dinb,
    output reg [63:0] doutb
);
    reg [63:0] mem [0:255];
    reg [63:0] q1_a, q2_a;
    reg [63:0] q1_b, q2_b;
    integer i;
    initial begin
        for (i = 0; i < 256; i = i + 1) mem[i] = 0;
    end

    always @(posedge clka) begin
        if (ena) begin
            if (wea) mem[addra] <= dina;
            q1_a <= mem[addra];
        end
        q2_a <= q1_a;
        douta <= q2_a;
    end

    always @(posedge clkb) begin
        if (enb) begin
            if (web) mem[addrb] <= dinb;
            q1_b <= mem[addrb];
        end
        q2_b <= q1_b;
        doutb <= q2_b;
    end
endmodule
