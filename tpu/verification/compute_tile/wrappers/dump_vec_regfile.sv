`timescale 1ns/1ps
module dump;
    initial begin
        $dumpfile("vec_regfile.vcd");
        $dumpvars(0, vec_regfile);
    end
endmodule
