`timescale 1ns/1ps

module dump;
    initial begin
        $dumpfile("pc.vcd");
        $dumpvars(0, pc);
    end
endmodule
