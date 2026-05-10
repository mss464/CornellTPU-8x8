`timescale 1ns / 1ps

module tb_dma_latency;

    reg clk, rst_n;
    always #5 clk = ~clk;

    // ── Shared state ───────────────────────────────────────────────────
    reg [31:0] len;
    wire [31:0] stream_len = {3'b000, len[31:3]};
    reg [255:0] bram [0:1023];
    reg [15:0] base_addr;
    reg latency_mode;

    // ── DMA Read Path ──────────────────────────────────────────────────
    wire        m_axis_tvalid;
    wire [255:0] m_axis_tdata;
    wire        m_axis_tlast;
    wire [31:0] m_axis_tstrb, m_axis_tkeep;
    reg         m_axis_tready;
    wire [15:0] read_pointer;
    wire        rd_cmd_valid;
    wire        read_bram_done;
    reg         mc_read_en;

    // BRAM Read Logic:
    // latency_mode = 0: 1 cycle (address at N, data at N+1)
    // latency_mode = 1: 2 cycles (address at N, data at N+2)
    reg [255:0] bram_data_q1, bram_data_q2;
    wire [15:0] rd_addr = base_addr[15:3] + {3'b000, read_pointer};

    always @(posedge clk) begin
        bram_data_q1 <= bram[rd_addr[9:0]];
        bram_data_q2 <= bram_data_q1;
    end

    wire [255:0] sys_rd_data = latency_mode ? bram_data_q2 : bram_data_q1;

    // Control pipeline (matches latency_mode)
    reg bram_latency_q1, bram_latency_q2;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            bram_latency_q1 <= 1'b0;
            bram_latency_q2 <= 1'b0;
        end else begin
            bram_latency_q1 <= rd_cmd_valid;
            bram_latency_q2 <= bram_latency_q1;
        end
    end
    wire device_mem_rd_valid = latency_mode ? bram_latency_q2 : bram_latency_q1;

    always @(posedge clk) begin
        if (mc_read_en) begin
            $display("T=%0t [TB] state=%0d reads=%0d sent=%0d empty=%b full=%b vld=%b rdy=%b", 
                     $time, u_master.state, u_master.reads_issued, u_master.beats_sent, 
                     u_master.fifo_empty, u_master.fifo_full, m_axis_tvalid, m_axis_tready);
        end
    end

    tpu_master_axi_stream #(
        .C_M_AXIS_TDATA_WIDTH(256)
    ) u_master (
        .M_AXIS_ACLK(clk),
        .M_AXIS_ARESETN(rst_n),
        .M_AXIS_TVALID(m_axis_tvalid),
        .M_AXIS_TDATA(m_axis_tdata),
        .M_AXIS_TSTRB(m_axis_tstrb),
        .M_AXIS_TKEEP(m_axis_tkeep),
        .M_AXIS_TLAST(m_axis_tlast),
        .M_AXIS_TREADY(m_axis_tready),
        .data_to_ddr(sys_rd_data),
        .len(stream_len),
        .read_en(mc_read_en),
        .done(read_bram_done),
        .read_pointer_stream(read_pointer),
        .rd_cmd_valid(rd_cmd_valid),
        .device_mem_rd_ready(1'b1),
        .device_mem_rd_valid(device_mem_rd_valid)
    );

    // ── Capture Results ───────────────────────────────────────────────
    integer beat_idx;
    reg [255:0] read_results [0:63];
    
    always @(posedge clk) begin
        if (m_axis_tvalid && m_axis_tready) begin
            read_results[beat_idx] <= m_axis_tdata;
            beat_idx <= beat_idx + 1;
        end
    end

    // ── Test Sequence ─────────────────────────────────────────────────
    integer i, errors;

    task run_test(input mode);
        begin
            latency_mode = mode;
            $display("\n>>> RUNNING TEST: Latency Mode = %0d", latency_mode);
            
            // Init BRAM with pattern
            for (i = 0; i < 16; i = i + 1) bram[i] = {224'd0, i[31:0]};

            // Start read
            len = 32; // 4 beats
            beat_idx = 0;
            mc_read_en <= 0;
            @(posedge clk);
            mc_read_en <= 1;
            
            // Wait for completion
            while (!read_bram_done) @(posedge clk);
            @(posedge clk);
            mc_read_en = 0;
            repeat(10) @(posedge clk);

            // Verify
            errors = 0;
            for (i = 0; i < 4; i = i + 1) begin
                if (read_results[i] !== {224'd0, i[31:0]}) begin
                    $display("  FAIL beat[%0d]: got %h, expected %h", i, read_results[i], {224'd0, i[31:0]});
                    errors = errors + 1;
                end else begin
                    $display("  PASS beat[%0d]", i);
                end
            end
            if (errors == 0) $display(">>> MODE %0d PASSED", latency_mode);
            else $display(">>> MODE %0d FAILED with %0d errors", latency_mode, errors);
        end
    endtask

    initial begin
        clk = 0;
        rst_n = 0;
        m_axis_tready = 1;
        mc_read_en = 0;
        base_addr = 0;
        
        #100 rst_n = 1;
        #100;

        run_test(0); // Test 1-cycle latency
        #100;
        run_test(1); // Test 2-cycle latency
        
        #100;
        $finish;
    end

endmodule
