`timescale 1ns / 1ps
// ============================================================================
// Integration test for the DMA write → read roundtrip
// Models device_mem BRAM behavior to verify data integrity
// ============================================================================
module tb_dma_roundtrip;

    reg clk, rst_n;
    always #5 clk = ~clk;

    // ── Shared state ───────────────────────────────────────────────────
    reg [31:0] len;           // 32-bit words
    wire [31:0] stream_len;   // 256-bit beats
    assign stream_len = {3'b000, len[31:3]};

    // ── Fake BRAM (8 banks x 32-bit = 256-bit wide) ───────────────────
    reg [255:0] bram [0:1023];
    reg [15:0] base_addr;

    // ── DMA Write Path (slave stream) ─────────────────────────────────
    wire        s_axis_tready;
    reg         s_axis_tvalid;
    reg [255:0] s_axis_tdata;
    reg         s_axis_tlast;
    wire [255:0] dma_wr_data;
    wire [15:0]  write_pointer;
    wire         write_bram_done;
    wire         stream_data_valid;
    reg          mc_data_write_en;

    tpu_slave_axi_stream #(
        .C_S_AXIS_TDATA_WIDTH(256)
    ) u_slave (
        .S_AXIS_ACLK(clk),
        .S_AXIS_ARESETN(rst_n),
        .S_AXIS_TREADY(s_axis_tready),
        .S_AXIS_TDATA(s_axis_tdata),
        .S_AXIS_TSTRB(32'hFFFFFFFF),
        .S_AXIS_TLAST(s_axis_tlast),
        .S_AXIS_TVALID(s_axis_tvalid),
        .len(stream_len),
        .data_to_bram(dma_wr_data),
        .data_to_iram(),
        .write_pointer_stream(write_pointer),
        .done(write_bram_done),
        .data_valid(stream_data_valid),
        .write_en(mc_data_write_en),
        .tpu_mode_stream(3'd1),  // MODE_DMA_WRITE
        .device_mem_ready(1'b1)
    );

    // BRAM write model
    wire dma_wr_en = mc_data_write_en && stream_data_valid;
    wire [15:0] wr_addr = base_addr[15:3] + {3'b000, write_pointer};
    always @(posedge clk) begin
        if (dma_wr_en) begin
            bram[wr_addr[9:0]] <= dma_wr_data;
            $display("T=%0t BRAM WRITE: addr=%0d data=%h", $time, wr_addr, dma_wr_data);
        end
    end

    // ── DMA Read Path (master stream) ─────────────────────────────────
    wire        m_axis_tvalid;
    wire [255:0] m_axis_tdata;
    wire        m_axis_tlast;
    wire [31:0] m_axis_tstrb, m_axis_tkeep;
    reg         m_axis_tready;
    wire [15:0] read_pointer;
    wire        rd_cmd_valid;
    wire        read_bram_done;
    reg         mc_read_en;

    // device_mem_rd_valid_q: 1-cycle delay of rd_cmd_valid (models BRAM latency)
    reg device_mem_rd_valid_q;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            device_mem_rd_valid_q <= 1'b0;
        else
            device_mem_rd_valid_q <= rd_cmd_valid;
    end

    // BRAM read model — synchronous 1-cycle latency
    // Matches Xilinx blk_mem_gen with Register_PortA_Output_of_Memory_Primitives = false
    // Address latched at posedge, data available combinationally before next posedge
    wire [15:0] rd_addr = base_addr[15:3] + {3'b000, read_pointer};
    reg [255:0] sys_rd_data;
    always @(posedge clk) begin
        sys_rd_data <= bram[rd_addr[9:0]];
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
        .device_mem_rd_valid(device_mem_rd_valid_q)
    );

    // ── Capture read results ──────────────────────────────────────────
    integer beat_idx;
    reg [255:0] read_results [0:63];
    
    always @(posedge clk) begin
        if (m_axis_tvalid && m_axis_tready) begin
            read_results[beat_idx] <= m_axis_tdata;
            $display("T=%0t READ BEAT[%0d]: data=%h TLAST=%b", $time, beat_idx, m_axis_tdata, m_axis_tlast);
            beat_idx <= beat_idx + 1;
        end
    end

    // ── Test Stimulus ─────────────────────────────────────────────────
    integer i;
    integer errors;

    task do_dma_write(input [31:0] num_beats);
        integer b;
        begin
            mc_data_write_en = 1;
            @(posedge clk); #1;
            for (b = 0; b < num_beats; b = b + 1) begin
                s_axis_tdata = {224'd0, b[15:0], b[15:0]};  // recognizable pattern
                s_axis_tvalid = 1;
                s_axis_tlast = (b == num_beats - 1);
                @(posedge clk);
                while (!s_axis_tready) @(posedge clk);
                #1;
            end
            s_axis_tvalid = 0;
            s_axis_tlast = 0;
            // Wait for write_bram_done
            repeat(5) @(posedge clk);
            mc_data_write_en = 0;
        end
    endtask

    task do_dma_read;
        begin
            beat_idx = 0;
            m_axis_tready = 1;
            @(posedge clk);
            #1 mc_read_en = 1;
            @(posedge clk);
            @(posedge clk);
            // Wait for done
            while (!read_bram_done) @(posedge clk);
            @(posedge clk);
            mc_read_en = 0;
        end
    endtask

    initial begin
        $dumpfile("tb_dma_roundtrip.vcd");
        $dumpvars(0, tb_dma_roundtrip);

        clk = 0;
        rst_n = 0;
        s_axis_tvalid = 0;
        s_axis_tdata = 0;
        s_axis_tlast = 0;
        m_axis_tready = 1;
        mc_data_write_en = 0;
        mc_read_en = 0;
        base_addr = 0;
        beat_idx = 0;
        len = 0;
        errors = 0;

        // Init BRAM to known bad pattern
        for (i = 0; i < 1024; i = i + 1) bram[i] = {8{32'hDEAD_BEEF}};

        #20 rst_n = 1;
        #20;

        // ================================================================
        // Test: Write 32 words (4 beats of 256-bit), then read them back
        // ================================================================
        $display("\n=== DMA WRITE: 32 words (4 x 256-bit beats) ===");
        len = 32;
        base_addr = 0;
        do_dma_write(4);

        $display("\n=== DMA READ: 32 words (4 x 256-bit beats) ===");
        do_dma_read;

        // Verify
        $display("\n=== VERIFICATION ===");
        for (i = 0; i < 4; i = i + 1) begin
            if (read_results[i] !== {224'd0, i[15:0], i[15:0]}) begin
                $display("FAIL beat[%0d]: got %h, expected %h", i, read_results[i], {224'd0, i[15:0], i[15:0]});
                errors = errors + 1;
            end else begin
                $display("PASS beat[%0d]: %h", i, read_results[i]);
            end
        end

        if (errors == 0)
            $display("\n*** ALL TESTS PASSED ***");
        else
            $display("\n*** %0d ERRORS ***", errors);

        #100;
        $finish;
    end

endmodule
