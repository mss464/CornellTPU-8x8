`timescale 1ns / 1ps

module tb_tpu_master_axi_stream;

    reg M_AXIS_ACLK;
    reg M_AXIS_ARESETN;
    
    wire M_AXIS_TVALID;
    wire [255:0] M_AXIS_TDATA;
    wire [31:0] M_AXIS_TSTRB;
    wire [31:0] M_AXIS_TKEEP;
    wire M_AXIS_TLAST;
    reg M_AXIS_TREADY;
    
    reg [31:0] len;
    
    // from BRAM
    reg [255:0] data_to_ddr;
    
    // to BRAM/mem_ctrl
    wire [15:0] read_pointer_stream;
    wire rd_cmd_valid;
    
    // from mem_ctrl
    reg device_mem_rd_ready;
    reg device_mem_rd_valid;
    
    reg read_en;
    wire done;

    tpu_master_axi_stream #(
        .C_M_AXIS_TDATA_WIDTH(256)
    ) dut (
        .M_AXIS_ACLK(M_AXIS_ACLK),
        .M_AXIS_ARESETN(M_AXIS_ARESETN),
        .M_AXIS_TVALID(M_AXIS_TVALID),
        .M_AXIS_TDATA(M_AXIS_TDATA),
        .M_AXIS_TSTRB(M_AXIS_TSTRB),
        .M_AXIS_TKEEP(M_AXIS_TKEEP),
        .M_AXIS_TLAST(M_AXIS_TLAST),
        .M_AXIS_TREADY(M_AXIS_TREADY),
        
        .len(len),
        .data_to_ddr(data_to_ddr),
        .read_pointer_stream(read_pointer_stream),
        .rd_cmd_valid(rd_cmd_valid),
        .device_mem_rd_ready(device_mem_rd_ready),
        .device_mem_rd_valid(device_mem_rd_valid),
        
        .read_en(read_en),
        .done(done)
    );

    // Clock generation
    always #5 M_AXIS_ACLK = ~M_AXIS_ACLK;
    
    // BRAM model: 1-cycle latency
    always @(posedge M_AXIS_ACLK) begin
        if (rd_cmd_valid && device_mem_rd_ready) begin
            device_mem_rd_valid <= 1'b1;
            data_to_ddr <= {224'd0, read_pointer_stream, read_pointer_stream};
        end else begin
            device_mem_rd_valid <= 1'b0;
        end
    end

    // Comprehensive per-cycle monitor
    always @(posedge M_AXIS_ACLK) begin
        $display("T=%0t | st=%0d rd_en=%b rise=%b flush=%b | ri=%0d b_rec=%0d b_sent=%0d | rdcmd=%b rdvld=%b wrEN=%b empty=%b afull=%b | TVAL=%b TRDY=%b TLAST=%b done=%b",
            $time,
            dut.state, read_en, dut.read_en_rise, dut.fifo_flush,
            dut.reads_issued, dut.beats_received_from_mem, dut.beats_sent,
            rd_cmd_valid, device_mem_rd_valid, dut.fifo_wr_en, dut.fifo_empty, dut.fifo_almost_full,
            M_AXIS_TVALID, M_AXIS_TREADY, M_AXIS_TLAST, done);
    end

    initial begin
        $dumpfile("tb_tpu_master_axi_stream.vcd");
        $dumpvars(0, tb_tpu_master_axi_stream);
        
        M_AXIS_ACLK = 0;
        M_AXIS_ARESETN = 0;
        M_AXIS_TREADY = 1;
        len = 0;
        data_to_ddr = 0;
        device_mem_rd_ready = 1;
        device_mem_rd_valid = 0;
        read_en = 0;
        
        #20 M_AXIS_ARESETN = 1;
        #20;
        
        // ========== Test 1: len = 4 ==========
        $display("\n=== Test 1: len = 4 ===");
        len = 4;
        @(posedge M_AXIS_ACLK);
        #1 read_en = 1;            // assert just after posedge
        @(posedge M_AXIS_ACLK);
        #1 read_en = 0;
        
        wait(done);
        @(posedge M_AXIS_ACLK);
        @(posedge M_AXIS_ACLK);
        @(posedge M_AXIS_ACLK);
        
        // ========== Test 2: len = 1 ==========
        $display("\n=== Test 2: len = 1 ===");
        len = 1;
        @(posedge M_AXIS_ACLK);
        #1 read_en = 1;
        @(posedge M_AXIS_ACLK);
        #1 read_en = 0;
        
        // Timeout
        repeat(20) @(posedge M_AXIS_ACLK);
        if (!done) begin
            $display("*** TIMEOUT: len=1 never completed! ***");
            $display("*** state=%0d reads_issued=%0d beats_sent=%0d fifo_empty=%b ***",
                dut.state, dut.reads_issued, dut.beats_sent, dut.fifo_empty);
        end
        
        $finish;
    end

endmodule
