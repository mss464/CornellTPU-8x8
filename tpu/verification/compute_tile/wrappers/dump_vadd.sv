`timescale 1ns/1ps

module dump;
    initial begin
        $dumpfile("vadd.vcd");
        $dumpvars(0, vadd);
    end
endmodule
