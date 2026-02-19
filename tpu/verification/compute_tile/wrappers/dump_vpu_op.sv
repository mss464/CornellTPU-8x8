`timescale 1ns/1ps

module dump;
    initial begin
        $dumpfile("vpu_op.vcd");
        $dumpvars(0, vpu_op);
    end
endmodule
