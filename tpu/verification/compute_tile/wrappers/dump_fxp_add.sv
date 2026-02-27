`timescale 1ns/1ps

module dump;
    initial begin
        $dumpfile("fxp_add.vcd");
        $dumpvars(0, fxp_add);
    end
endmodule
