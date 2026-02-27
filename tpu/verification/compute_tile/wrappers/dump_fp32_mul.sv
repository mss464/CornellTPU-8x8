`timescale 1ns/1ps

module dump;
    initial begin
        $dumpfile("fp32_mul.vcd");
        $dumpvars(0, fp32_mul);
    end
endmodule
