`timescale 1ns/1ps

module dump;
    initial begin
        $dumpfile("fifo4.vcd");
        $dumpvars(0, fifo4);
    end
endmodule
