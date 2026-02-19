`timescale 1ns/1ps

module dump;
    initial begin
        $dumpfile("decoder.vcd");
        $dumpvars(0, decoder);
    end
endmodule
