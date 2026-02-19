`timescale 1ns/1ps
module dump;
    initial begin
        $dumpfile("vpu_simd.vcd");
        $dumpvars(0, vpu_simd);
    end
endmodule
