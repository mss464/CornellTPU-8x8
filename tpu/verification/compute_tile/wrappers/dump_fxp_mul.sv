`timescale 1ns/1ps

module dump;
    initial begin
        $dumpfile("fxp_mul.vcd");
        $dumpvars(0, fxp_mul);
    end
endmodule
