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
    output reg  [15:0] read_pointer_stream,

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
    wire [255:0] fifo_rd_data;
    wire        fifo_full;
    wire        fifo_empty;
    wire        fifo_almost_full;
    reg         fifo_flush;

    fifo4 #(.WIDTH(256), .DEPTH(64)) u_fifo (
        .clk         (M_AXIS_ACLK),
        .rst_n       (M_AXIS_ARESETN),
        .flush       (fifo_flush),
        .wr_en       (fifo_wr_en),
        .wr_data     (fifo_wr_data),
        .rd_en       (fifo_rd_en),
        .rd_data     (fifo_rd_data),
        .full        (fifo_full),
        .empty       (fifo_empty),
        .almost_full (fifo_almost_full)
    );

    // =========================================================================
    // BRAM data pipeline — 1-cycle latency tracking
    // =========================================================================
    // bram_reading: asserted when we have a valid address on read_pointer_stream
    //   this cycle. data_to_ddr will be valid on the NEXT cycle.
    // bram_data_valid: delayed bram_reading — marks when data_to_ddr is valid.
    reg bram_data_valid;
    reg bram_reading;

    always @(posedge M_AXIS_ACLK) begin
        if (!M_AXIS_ARESETN)
            bram_data_valid <= 1'b0;
        else
            bram_data_valid <= bram_reading;
    end

    // FIFO write: capture BRAM data when valid
    assign fifo_wr_en   = bram_data_valid && !fifo_full;
    assign fifo_wr_data = data_to_ddr;

    // =========================================================================
    // BRAM address tracking
    // =========================================================================
    // reads_issued: how many BRAM reads we have issued (address presented)
    // read_pointer_stream: the BRAM address output (visible externally)
    reg [31:0] reads_issued;

    // =========================================================================
    // Beat counter — counts AXI handshakes
    // =========================================================================
    reg [31:0] beats_sent;

    // =========================================================================
    // AXI-Stream output (FWFT — no pipeline stage)
    // =========================================================================
    assign M_AXIS_TVALID = !fifo_empty && (state == S_STREAM);
    assign M_AXIS_TDATA  = fifo_rd_data;
    assign M_AXIS_TSTRB  = {(C_M_AXIS_TDATA_WIDTH/8){1'b1}};
    assign M_AXIS_TKEEP  = {(C_M_AXIS_TDATA_WIDTH/8){1'b1}};
    assign M_AXIS_TLAST  = M_AXIS_TVALID && (beats_sent == len - 1);

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
            read_pointer_stream <= 16'd0;
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
                    read_pointer_stream <= 16'd0;
                    reads_issued        <= 32'd0;
                    beats_sent          <= 32'd0;

                    if (read_en_rise) begin
                        fifo_flush   <= 1'b0;  // stop flushing on transition
                        bram_reading <= 1'b1;  // present address 0 this cycle
                        // read_pointer_stream stays 0 — that's our first address
                        reads_issued <= 32'd1; // we've issued 1 read
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
                    if (reads_issued < len && !fifo_almost_full) begin
                        read_pointer_stream <= reads_issued[15:0];
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
                    if (reads_issued < len && !fifo_almost_full) begin
                        read_pointer_stream <= reads_issued[15:0];
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
