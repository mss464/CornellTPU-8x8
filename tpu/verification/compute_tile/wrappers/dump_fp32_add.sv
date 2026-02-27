`timescale 1ns/1ps

module dump;
    initial begin
        $dumpfile("fp32_add.vcd");
        $dumpvars(0, fp32_add);
    end
endmodule
