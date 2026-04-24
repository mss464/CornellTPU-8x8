// ============================================================================
// tpu_master_axi_stream.v — AXI-Stream master (DMA read path: BRAM → host)
//
// Clean rewrite of the Xilinx template. 3-state FSM: IDLE → FILL → STREAM.
//
// Architecture:
//   BRAM reader FSM → FIFO (FWFT) → AXI-Stream output
//
// Key features:
//   - M_AXIS_TKEEP driven (critical for Xilinx DMA S2MM)
//   - FWFT FIFO eliminates pipeline delay between FIFO and AXI output
//   - No INIT_COUNTER startup delay — FILL state pre-fills FIFO precisely
//   - Rising-edge detector on read_en prevents re-trigger race
//
// BRAM timing model:
//   read_pointer_stream is driven as the BRAM address.  Between posedges,
//   the external memory (device_mem / testbench) sees this value and drives
//   data_to_ddr combinationally.  On the NEXT posedge the RTL captures
//   data_to_ddr into the FIFO — this is the 1-cycle BRAM read latency.
//
//   Cycle N (posedge): FSM asserts bram_reading, read_pointer_stream = A
//   Between N..N+1:    TB/BRAM drives data_to_ddr = mem[A]
//   Cycle N+1 (posedge): bram_data_valid = 1, FIFO captures data_to_ddr
//                         FSM increments read_pointer_stream to A+1
// ============================================================================

`timescale 1 ns / 1 ps

module tpu_master_axi_stream #(
    parameter integer C_M_AXIS_TDATA_WIDTH = 256
)(
    // User ports
    input  wire [255:0] data_to_ddr,
    input  wire [31:0] len,
    input  wire        read_en,
    output wire        done,
    output wire [15:0] read_pointer_stream,
    output wire        rd_cmd_valid,         // pulsed 1 cycle when a new read is issued
    // Device memory AXI handshake (LPDDR4-aware)
    input  wire        device_mem_rd_ready,  // device_mem can accept a new read
    input  wire        device_mem_rd_valid,  // device_mem has valid read data

    // AXI-Stream master ports
    input  wire        M_AXIS_ACLK,
    input  wire        M_AXIS_ARESETN,
    output wire        M_AXIS_TVALID,
    output wire [C_M_AXIS_TDATA_WIDTH-1:0]   M_AXIS_TDATA,
    output wire [(C_M_AXIS_TDATA_WIDTH/8)-1:0] M_AXIS_TSTRB,
    output wire [(C_M_AXIS_TDATA_WIDTH/8)-1:0] M_AXIS_TKEEP,
    output wire        M_AXIS_TLAST,
    input  wire        M_AXIS_TREADY
);

    // =========================================================================
    // FSM states
    // =========================================================================
    localparam [1:0] S_IDLE   = 2'd0,
                     S_FILL   = 2'd1,
                     S_STREAM = 2'd2;

    reg [1:0] state;

    // =========================================================================
    // Rising-edge detector for read_en (prevents re-trigger race)
    // =========================================================================
    reg read_en_prev;
    wire read_en_rise = read_en && !read_en_prev;

    always @(posedge M_AXIS_ACLK) begin
        if (!M_AXIS_ARESETN)
            read_en_prev <= 1'b0;
        else
            read_en_prev <= read_en;
    end

    // =========================================================================
    // FIFO instance (FWFT, depth=64, synchronous flush)
    // =========================================================================
    wire        fifo_wr_en;
    wire [255:0] fifo_wr_data;
    wire        fifo_rd_en;
    wire [256:0] fifo_rdata;
    wire        fifo_full;
    wire        fifo_empty;
    wire        fifo_almost_full;
    reg         fifo_flush;
    reg  [31:0] beats_received_from_mem;

    fifo4 #(
        .WIDTH(257),
        .DEPTH(64)
    ) u_fifo (
        .clk         (M_AXIS_ACLK),
        .rst_n       (M_AXIS_ARESETN),
        .flush       (fifo_flush),
        .wr_en       (fifo_wr_en),
        .wr_data     ({ (beats_received_from_mem == len - 1), data_to_ddr }),
        .rd_en       (fifo_rd_en),
        .rd_data     (fifo_rdata),
        .full        (fifo_full),
        .empty       (fifo_empty),
        .almost_full (fifo_almost_full)
    );

    // =========================================================================
    // Track number of beats received to calculate TLAST properly without pipeline slip
    // =========================================================================

    always @(posedge M_AXIS_ACLK) begin
        if (!M_AXIS_ARESETN || fifo_flush) begin
            beats_received_from_mem <= 32'd0;
        end else if (fifo_wr_en) begin
            beats_received_from_mem <= beats_received_from_mem + 1'b1;
        end
    end

    // =========================================================================
    // Read data pipeline — AXI4 LPDDR4 aware
    // =========================================================================
    // bram_reading: asserted when we have issued a read command to device_mem
    //   this cycle (device_mem_rd_ready was checked before asserting).
    // Data validity is now signalled by device_mem_rd_valid (variable latency)
    //   instead of a fixed 1-cycle delay.
    reg bram_reading;
    wire do_issue_read = (state == S_IDLE && read_en_rise && device_mem_rd_ready) || 
                         ((state == S_FILL || state == S_STREAM) && (reads_issued < len) && !fifo_almost_full && device_mem_rd_ready);
    assign rd_cmd_valid = do_issue_read;

    // FIFO write: capture device memory data when AXI response arrives
    assign fifo_wr_en   = device_mem_rd_valid && !fifo_full;

    // =========================================================================
    // BRAM address tracking
    // =========================================================================
    // reads_issued: how many BRAM reads we have issued (address presented)
    // read_pointer_stream: the BRAM address output (visible externally)
    reg [31:0] reads_issued;
    assign read_pointer_stream = reads_issued[15:0];

    // =========================================================================
    // Beat counter — counts AXI handshakes
    // =========================================================================
    reg [31:0] beats_sent;

    // =========================================================================
    // AXI-Stream output (FWFT — no pipeline stage)
    // =========================================================================
    assign M_AXIS_TVALID = !fifo_empty && (state == S_STREAM);
    assign M_AXIS_TDATA  = fifo_rdata[255:0];
    assign M_AXIS_TSTRB  = {(C_M_AXIS_TDATA_WIDTH/8){1'b1}};
    assign M_AXIS_TKEEP  = {(C_M_AXIS_TDATA_WIDTH/8){1'b1}};
    assign M_AXIS_TLAST  = fifo_rdata[256];

    // FIFO read: consume on AXI handshake
    assign fifo_rd_en = M_AXIS_TVALID && M_AXIS_TREADY;

    // Done: all beats sent
    reg done_reg;
    assign done = done_reg;

    // =========================================================================
    // Main FSM
    // =========================================================================
    always @(posedge M_AXIS_ACLK) begin
        if (!M_AXIS_ARESETN) begin
            state               <= S_IDLE;
            reads_issued        <= 32'd0;
            beats_sent          <= 32'd0;
            done_reg            <= 1'b0;
            fifo_flush          <= 1'b0;
            bram_reading        <= 1'b0;
        end else begin
            // Defaults
            fifo_flush   <= 1'b0;
            bram_reading <= 1'b0;

            case (state)
                // =============================================================
                // IDLE: wait for read_en rising edge
                // =============================================================
                S_IDLE: begin
                    done_reg            <= 1'b0;
                    fifo_flush          <= 1'b1;  // clear FIFO
                    reads_issued        <= 32'd0;
                    beats_sent          <= 32'd0;

                    if (read_en_rise) begin
                        fifo_flush   <= 1'b0;  // stop flushing on transition
                        // Issue first read only if device_mem is ready
                        if (device_mem_rd_ready) begin
                            $display("[%0t] tpu_master_axi_stream S_IDLE -> S_FILL (len = %0d)", $time, len);
                            bram_reading <= 1'b1;  // present address 0 this cycle
                            reads_issued <= 32'd1; // we've issued 1 read
                        end
                        state        <= S_FILL;
                    end
                end

                // =============================================================
                // FILL: pre-fill FIFO with a few BRAM words before streaming.
                // BRAM has 1-cycle latency: address on cycle N → data on N+1.
                // We issue reads and wait until FIFO has at least 1 entry.
                // =============================================================
                S_FILL: begin
                    // Advance pointer (data for previous address captured by
                    // bram_data_valid on this cycle; present next address)
                    if (reads_issued < len && !fifo_almost_full && device_mem_rd_ready) begin
                        bram_reading        <= 1'b1;
                        reads_issued        <= reads_issued + 1'b1;
                    end

                    // Transition when FIFO has data (FWFT: !empty means valid)
                    if (!fifo_empty) begin
                        state <= S_STREAM;
                    end
                end

                // =============================================================
                // STREAM: drive AXI-Stream output, continue BRAM reads
                // =============================================================
                S_STREAM: begin
                    // Continue BRAM reads (flow-control: pause when FIFO almost full)
                    if (reads_issued < len && !fifo_almost_full && device_mem_rd_ready) begin
                        bram_reading        <= 1'b1;
                        reads_issued        <= reads_issued + 1'b1;
                    end

                    // Count AXI handshakes
                    if (M_AXIS_TVALID && M_AXIS_TREADY) begin
                        beats_sent <= beats_sent + 1'b1;

                        // Check if this was the last beat
                        if (beats_sent == len - 1) begin
                            done_reg <= 1'b1;
                            state    <= S_IDLE;
                        end
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
