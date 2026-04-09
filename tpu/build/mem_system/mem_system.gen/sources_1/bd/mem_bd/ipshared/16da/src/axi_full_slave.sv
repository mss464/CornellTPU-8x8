`timescale 1 ns / 1 ps
// ============================================================================
// axi_full_slave.sv — AXI4 Full Slave Interface
//
// Provides direct MMIO read/write access to system memory via the PS AXI
// master port. Supports single-beat and INCR burst transactions.
//
// Data width: 32-bit
// Address width: parameterizable (default 18 = 256 KB address space)
//
// The module translates AXI4 transactions into simple BRAM-style signals:
//   mem_addr, mem_din, mem_dout, mem_en, mem_we
// ============================================================================

module axi_full_slave #(
    parameter integer C_S_AXI_DATA_WIDTH = 32,
    parameter integer C_S_AXI_ADDR_WIDTH = 18   // 256KB address space
)(
    // ── AXI4 Global Signals ─────────────────────────────────────────
    input  wire                                S_AXI_ACLK,
    input  wire                                S_AXI_ARESETN,

    // ── Write Address Channel ───────────────────────────────────────
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]       S_AXI_AWADDR,
    input  wire [7:0]                          S_AXI_AWLEN,
    input  wire [2:0]                          S_AXI_AWSIZE,
    input  wire [1:0]                          S_AXI_AWBURST,
    input  wire                                S_AXI_AWVALID,
    output reg                                 S_AXI_AWREADY,

    // ── Write Data Channel ──────────────────────────────────────────
    input  wire [C_S_AXI_DATA_WIDTH-1:0]       S_AXI_WDATA,
    input  wire [(C_S_AXI_DATA_WIDTH/8)-1:0]   S_AXI_WSTRB,
    input  wire                                S_AXI_WLAST,
    input  wire                                S_AXI_WVALID,
    output reg                                 S_AXI_WREADY,

    // ── Write Response Channel ──────────────────────────────────────
    output reg  [1:0]                          S_AXI_BRESP,
    output reg                                 S_AXI_BVALID,
    input  wire                                S_AXI_BREADY,

    // ── Read Address Channel ────────────────────────────────────────
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]       S_AXI_ARADDR,
    input  wire [7:0]                          S_AXI_ARLEN,
    input  wire [2:0]                          S_AXI_ARSIZE,
    input  wire [1:0]                          S_AXI_ARBURST,
    input  wire                                S_AXI_ARVALID,
    output reg                                 S_AXI_ARREADY,

    // ── Read Data Channel ───────────────────────────────────────────
    output reg  [C_S_AXI_DATA_WIDTH-1:0]       S_AXI_RDATA,
    output reg  [1:0]                          S_AXI_RRESP,
    output reg                                 S_AXI_RLAST,
    output reg                                 S_AXI_RVALID,
    input  wire                                S_AXI_RREADY,

    // ── Memory Interface ────────────────────────────────────────────
    output reg  [15:0]                         mem_addr,    // word address
    output reg  [31:0]                         mem_din,
    input  wire [31:0]                         mem_dout,
    output reg                                 mem_en,
    output reg                                 mem_we
);

    // Address LSB for 32-bit data alignment
    localparam ADDR_LSB = 2;  // byte address → word address shift

    // ── Write FSM ───────────────────────────────────────────────────
    localparam [1:0] WR_IDLE    = 2'd0,
                     WR_DATA    = 2'd1,
                     WR_RESP    = 2'd2;

    reg [1:0]  wr_state;
    reg [C_S_AXI_ADDR_WIDTH-1:0] wr_addr;
    reg [7:0]  wr_beat_cnt;
    reg [7:0]  wr_len;

    // ── Read FSM ────────────────────────────────────────────────────
    localparam [1:0] RD_IDLE    = 2'd0,
                     RD_ISSUE   = 2'd1,  // issue BRAM read
                     RD_DATA    = 2'd2;  // present data on RDATA

    reg [1:0]  rd_state;
    reg [C_S_AXI_ADDR_WIDTH-1:0] rd_addr;
    reg [7:0]  rd_beat_cnt;
    reg [7:0]  rd_len;
    reg        rd_mem_valid;   // BRAM data valid after 1-cycle latency

    // Priority: write FSM owns mem port when writing, read FSM when reading
    // Simple priority: writes take precedence (avoid read/write collision)
    wire wr_active = (wr_state == WR_DATA);

    // ── Write State Machine ─────────────────────────────────────────
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            wr_state     <= WR_IDLE;
            S_AXI_AWREADY <= 1'b0;
            S_AXI_WREADY  <= 1'b0;
            S_AXI_BVALID  <= 1'b0;
            S_AXI_BRESP   <= 2'b00;
            wr_addr       <= 0;
            wr_beat_cnt   <= 0;
            wr_len        <= 0;
        end else begin
            case (wr_state)
                WR_IDLE: begin
                    S_AXI_AWREADY <= 1'b1;
                    S_AXI_WREADY  <= 1'b0;
                    S_AXI_BVALID  <= 1'b0;
                    if (S_AXI_AWVALID && S_AXI_AWREADY) begin
                        wr_addr       <= S_AXI_AWADDR;
                        wr_len        <= S_AXI_AWLEN;
                        wr_beat_cnt   <= 0;
                        S_AXI_AWREADY <= 1'b0;
                        S_AXI_WREADY  <= 1'b1;
                        wr_state      <= WR_DATA;
                    end
                end

                WR_DATA: begin
                    if (S_AXI_WVALID && S_AXI_WREADY) begin
                        // Write accepted
                        wr_beat_cnt <= wr_beat_cnt + 8'd1;
                        wr_addr     <= wr_addr + (1 << ADDR_LSB);  // next word
                        if (S_AXI_WLAST || wr_beat_cnt == wr_len) begin
                            S_AXI_WREADY <= 1'b0;
                            S_AXI_BVALID <= 1'b1;
                            S_AXI_BRESP  <= 2'b00;  // OKAY
                            wr_state     <= WR_RESP;
                        end
                    end
                end

                WR_RESP: begin
                    if (S_AXI_BREADY && S_AXI_BVALID) begin
                        S_AXI_BVALID <= 1'b0;
                        wr_state     <= WR_IDLE;
                    end
                end

                default: wr_state <= WR_IDLE;
            endcase
        end
    end

    // ── Read State Machine ──────────────────────────────────────────
    always @(posedge S_AXI_ACLK) begin
        if (!S_AXI_ARESETN) begin
            rd_state      <= RD_IDLE;
            S_AXI_ARREADY <= 1'b0;
            S_AXI_RVALID  <= 1'b0;
            S_AXI_RLAST   <= 1'b0;
            S_AXI_RRESP   <= 2'b00;
            S_AXI_RDATA   <= 0;
            rd_addr       <= 0;
            rd_beat_cnt   <= 0;
            rd_len        <= 0;
            rd_mem_valid  <= 1'b0;
        end else begin
            rd_mem_valid <= 1'b0;

            case (rd_state)
                RD_IDLE: begin
                    S_AXI_ARREADY <= 1'b1;
                    S_AXI_RVALID  <= 1'b0;
                    S_AXI_RLAST   <= 1'b0;
                    if (S_AXI_ARVALID && S_AXI_ARREADY) begin
                        rd_addr       <= S_AXI_ARADDR;
                        rd_len        <= S_AXI_ARLEN;
                        rd_beat_cnt   <= 0;
                        S_AXI_ARREADY <= 1'b0;
                        rd_state      <= RD_ISSUE;
                    end
                end

                RD_ISSUE: begin
                    // Wait if write is active (write priority)
                    if (!wr_active) begin
                        rd_mem_valid <= 1'b1;
                        rd_state     <= RD_DATA;
                    end
                end

                RD_DATA: begin
                    if (rd_mem_valid) begin
                        // BRAM data valid — present on RDATA
                        S_AXI_RDATA  <= mem_dout;
                        S_AXI_RVALID <= 1'b1;
                        S_AXI_RRESP  <= 2'b00;
                        S_AXI_RLAST  <= (rd_beat_cnt == rd_len);
                    end

                    if (S_AXI_RVALID && S_AXI_RREADY) begin
                        S_AXI_RVALID <= 1'b0;
                        rd_beat_cnt  <= rd_beat_cnt + 8'd1;
                        rd_addr      <= rd_addr + (1 << ADDR_LSB);

                        if (rd_beat_cnt == rd_len) begin
                            // Transfer complete
                            rd_state <= RD_IDLE;
                        end else begin
                            rd_state <= RD_ISSUE;
                        end
                    end
                end

                default: rd_state <= RD_IDLE;
            endcase
        end
    end

    // ── Memory Port Mux ─────────────────────────────────────────────
    // Writes take priority over reads for the memory port
    always @(*) begin
        mem_addr = 16'd0;
        mem_din  = 32'd0;
        mem_en   = 1'b0;
        mem_we   = 1'b0;

        if (wr_state == WR_DATA && S_AXI_WVALID && S_AXI_WREADY) begin
            // Write transaction
            mem_addr = wr_addr[ADDR_LSB +: 16];
            mem_din  = S_AXI_WDATA;
            mem_en   = 1'b1;
            mem_we   = 1'b1;
        end else if (rd_state == RD_ISSUE && !wr_active) begin
            // Read transaction — issue BRAM read
            mem_addr = rd_addr[ADDR_LSB +: 16];
            mem_en   = 1'b1;
            mem_we   = 1'b0;
        end
    end

endmodule
