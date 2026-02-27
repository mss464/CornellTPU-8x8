`timescale 1 ns / 1 ps
// ============================================================================
// tpu.sv — TPU top-level: AXI glue + thin concurrent arbiter  (P2.08)
//
// Instantiates structural sub-modules (AXI slaves/master, memory tiles,
// compute tile) and three independent sub-FSMs:
//
//   dma_engine   — modes 1/2/4/5/6: host DMA and DevMem↔L2 transfers
//   compute_ctrl — mode  3:         compute tile execution
//   l2_ctrl      — modes 7/8:       L2↔L1 burst block copies
//
// All three sub-FSMs own disjoint BRAM ports and may run concurrently:
//   device_mem : Port A = dma_engine  / Port B = l2_tile tma_engine
//   L2 SRAM   : Port A = l2_ctrl     / Port B = l2_tile tma_engine
//   L1 BRAM   : Port A = l2_ctrl DMA / Port B = tensorcore compute
//
// Arbiter dispatch rules (doorbell-triggered):
//   DMA modes  (1/2/4/5/6) → dma_engine   if !dma_running
//   Compute    (3)          → compute_ctrl if !compute_running
//   L2 modes   (7/8)        → l2_ctrl      if !l2_running
//   Concurrent dispatch is allowed: e.g. mode-3 can run while mode-1 runs.
//   Within each group only one operation at a time (software contract).
//
// instr_ready = !dma_running && !compute_running && !l2_running
//   (backward-compatible with single-instr-at-a-time driver)
// ============================================================================

module tpu #
(
    parameter integer C_S00_AXI_DATA_WIDTH  = 32,
    parameter integer C_S00_AXI_ADDR_WIDTH  = 6,
    parameter integer C_S00_AXIS_TDATA_WIDTH = 32,
    parameter integer C_M00_AXIS_TDATA_WIDTH = 32,
    parameter integer C_M00_AXIS_START_COUNT = 32
)
(
    // AXI-Lite slave
    input  wire        s00_axi_aclk,
    input  wire        s00_axi_aresetn,
    input  wire [C_S00_AXI_ADDR_WIDTH-1:0] s00_axi_awaddr,
    input  wire [2:0]  s00_axi_awprot,
    input  wire        s00_axi_awvalid,
    output wire        s00_axi_awready,
    input  wire [C_S00_AXI_DATA_WIDTH-1:0] s00_axi_wdata,
    input  wire [(C_S00_AXI_DATA_WIDTH/8)-1:0] s00_axi_wstrb,
    input  wire        s00_axi_wvalid,
    output wire        s00_axi_wready,
    output wire [1:0]  s00_axi_bresp,
    output wire        s00_axi_bvalid,
    input  wire        s00_axi_bready,
    input  wire [C_S00_AXI_ADDR_WIDTH-1:0] s00_axi_araddr,
    input  wire [2:0]  s00_axi_arprot,
    input  wire        s00_axi_arvalid,
    output wire        s00_axi_arready,
    output wire [C_S00_AXI_DATA_WIDTH-1:0] s00_axi_rdata,
    output wire [1:0]  s00_axi_rresp,
    output wire        s00_axi_rvalid,
    input  wire        s00_axi_rready,

    // AXI-Stream slave (DMA write path)
    input  wire        s00_axis_aclk,
    input  wire        s00_axis_aresetn,
    output wire        s00_axis_tready,
    input  wire [C_S00_AXIS_TDATA_WIDTH-1:0] s00_axis_tdata,
    input  wire [(C_S00_AXIS_TDATA_WIDTH/8)-1:0] s00_axis_tstrb,
    input  wire        s00_axis_tlast,
    input  wire        s00_axis_tvalid,

    // AXI-Stream master (DMA read path)
    input  wire        m00_axis_aclk,
    input  wire        m00_axis_aresetn,
    output wire        m00_axis_tvalid,
    output wire [C_M00_AXIS_TDATA_WIDTH-1:0] m00_axis_tdata,
    output wire [(C_M00_AXIS_TDATA_WIDTH/8)-1:0] m00_axis_tstrb,
    output wire        m00_axis_tlast,
    input  wire        m00_axis_tready
);

    // =========================================================================
    // AXI-Lite register buses
    // =========================================================================
    wire [31:0] slv_reg0_bus;
    wire [31:0] slv_reg3_bus;
    wire [31:0] slv_reg4_bus;
    wire [31:0] slv_reg5_bus;
    wire [31:0] slv_reg6_bus;

    wire [12:0] addr_ram    = slv_reg3_bus[12:0];
    wire [15:0] addr_devmem = slv_reg4_bus[15:0];
    wire [14:0] addr_l2     = slv_reg5_bus[14:0];
    wire [31:0] dma_len     = slv_reg6_bus;

    wire [3:0]  tpu_mode    = slv_reg0_bus[3:0];

    // Doorbell mechanism
    wire        doorbell;
    reg         doorbell_clear;

    // Mode constants
    localparam MODE_IDLE      = 4'd0;
    localparam MODE_WR_DEVMEM = 4'd1;
    localparam MODE_RD_DEVMEM = 4'd2;
    localparam MODE_COMPUTE   = 4'd3;
    localparam MODE_WR_IRAM   = 4'd4;
    localparam MODE_DM2L2     = 4'd5;
    localparam MODE_L22DM     = 4'd6;
    localparam MODE_L22L1     = 4'd7;
    localparam MODE_L12L2     = 4'd8;

    // =========================================================================
    // Arbiter state
    // =========================================================================
    reg        dma_running;
    reg        compute_running;
    reg        l2_running;

    reg        dma_start;
    reg        compute_start;
    reg        l2_start;

    reg [3:0]  latched_mode;   // mode latched at doorbell acceptance

    // instr_ready: all sub-FSMs idle (backward-compatible)
    wire instr_ready_w = !dma_running && !compute_running && !l2_running;

    // =========================================================================
    // Sub-FSM wires
    // =========================================================================
    wire       dma_done;
    wire       compute_done;
    wire       l2_done;

    wire       dma_stream_ready;
    wire       dma_data_write_en;
    wire       dma_instr_write_en;
    wire       dma_start_stream;
    wire       dma_read_en;
    wire [7:0] dma_iram_addr;
    wire       dma_start_dm_to_l2;
    wire       dma_start_l2_to_dm;

    wire       cc_start_compute_tile;

    wire [14:0] lc_l2_ct_addr;
    wire        lc_l2_ct_en;
    wire        lc_l2_ct_we;
    wire [31:0] lc_l2_ct_din;
    wire [31:0] lc_l2_ct_dout;

    wire        lc_l1_dma_wr_en;
    wire [31:0] lc_l1_dma_wr_data;
    wire [15:0] lc_l1_dma_write_ptr;
    wire        lc_l1_dma_rd_en;
    wire [31:0] lc_l1_dma_rd_data;
    wire [15:0] lc_l1_dma_read_ptr;

    // =========================================================================
    // AXI-Stream plumbing wires
    // =========================================================================
    wire [15:0] write_pointer;
    wire [15:0] read_pointer;
    wire [31:0] dma_dram_din;
    wire [63:0] dma_iram_din;
    wire        stream_data_valid;
    wire        write_bram_done;
    wire        read_bram_done;
    wire [31:0] devmem_rd_data;

    // TMA signals
    wire        ct_tma_req;
    wire        ct_tma_dir;
    wire [15:0] ct_tma_dm_base;
    wire [14:0] ct_tma_l2_base;
    wire [15:0] ct_tma_len;
    wire        l2_tma_done;

    // DevMem Port B (L2 tile)
    wire [15:0] dm_l2_addr;
    wire [31:0] dm_l2_din;
    wire [31:0] dm_l2_dout;
    wire        dm_l2_en;
    wire        dm_l2_we;

    wire        xfer_l2_done;
    wire        compute_tile_done;

    // =========================================================================
    // Concurrent arbiter FSM
    // =========================================================================
    always @(posedge s00_axi_aclk or negedge s00_axi_aresetn) begin
        if (!s00_axi_aresetn) begin
            dma_running     <= 1'b0;
            compute_running <= 1'b0;
            l2_running      <= 1'b0;
            dma_start       <= 1'b0;
            compute_start   <= 1'b0;
            l2_start        <= 1'b0;
            doorbell_clear  <= 1'b0;
            latched_mode    <= 4'd0;
        end else begin
            // Pulse defaults
            dma_start      <= 1'b0;
            compute_start  <= 1'b0;
            l2_start       <= 1'b0;
            doorbell_clear <= 1'b0;

            // ----------------------------------------------------------------
            // Track sub-FSM completions (clear running first; dispatch below
            // may override back to 1 via last-NBA-wins if same cycle).
            // ----------------------------------------------------------------
            if (dma_done)     dma_running     <= 1'b0;
            if (compute_done) compute_running <= 1'b0;
            if (l2_done)      l2_running      <= 1'b0;

            // ----------------------------------------------------------------
            // Dispatch on doorbell.
            // Doorbell is always cleared immediately (host gets a response).
            // Each group is independent; different groups can be dispatched
            // while other groups are still running.
            // If a group is already busy (running and not done this cycle),
            // the doorbell is cleared but the command is silently dropped —
            // software contract: do not issue two commands to the same group
            // simultaneously.
            // ----------------------------------------------------------------
            if (doorbell) begin
                doorbell_clear <= 1'b1;
                latched_mode   <= tpu_mode;

                case (tpu_mode)
                    // --------------------------------------------------------
                    // DMA group: modes 1, 2, 4, 5, 6
                    // --------------------------------------------------------
                    MODE_WR_DEVMEM,
                    MODE_RD_DEVMEM,
                    MODE_WR_IRAM,
                    MODE_DM2L2,
                    MODE_L22DM: begin
                        if (!dma_running || dma_done) begin
                            dma_running <= 1'b1;  // last-NBA wins over done-clear above
                            dma_start   <= 1'b1;
                        end
                    end

                    // --------------------------------------------------------
                    // Compute group: mode 3
                    // --------------------------------------------------------
                    MODE_COMPUTE: begin
                        if (!compute_running || compute_done) begin
                            compute_running <= 1'b1;
                            compute_start   <= 1'b1;
                        end
                    end

                    // --------------------------------------------------------
                    // L2 group: modes 7, 8
                    // --------------------------------------------------------
                    MODE_L22L1,
                    MODE_L12L2: begin
                        if (!l2_running || l2_done) begin
                            l2_running <= 1'b1;
                            l2_start   <= 1'b1;
                        end
                    end

                    default: ; // unknown mode — doorbell cleared, nothing started
                endcase
            end
        end
    end

    // =========================================================================
    // AXI-Lite slave
    // =========================================================================
    tpu_slave_axi_lite #(
        .C_S_AXI_DATA_WIDTH(C_S00_AXI_DATA_WIDTH),
        .C_S_AXI_ADDR_WIDTH(C_S00_AXI_ADDR_WIDTH)
    ) tpu_slave_axi_lite_inst (
        .S_AXI_ACLK    (s00_axi_aclk),
        .S_AXI_ARESETN (s00_axi_aresetn),
        .S_AXI_AWADDR  (s00_axi_awaddr),
        .S_AXI_AWPROT  (s00_axi_awprot),
        .S_AXI_AWVALID (s00_axi_awvalid),
        .S_AXI_AWREADY (s00_axi_awready),
        .S_AXI_WDATA   (s00_axi_wdata),
        .S_AXI_WSTRB   (s00_axi_wstrb),
        .S_AXI_WVALID  (s00_axi_wvalid),
        .S_AXI_WREADY  (s00_axi_wready),
        .S_AXI_BRESP   (s00_axi_bresp),
        .S_AXI_BVALID  (s00_axi_bvalid),
        .S_AXI_BREADY  (s00_axi_bready),
        .S_AXI_ARADDR  (s00_axi_araddr),
        .S_AXI_ARPROT  (s00_axi_arprot),
        .S_AXI_ARVALID (s00_axi_arvalid),
        .S_AXI_ARREADY (s00_axi_arready),
        .S_AXI_RDATA   (s00_axi_rdata),
        .S_AXI_RRESP   (s00_axi_rresp),
        .S_AXI_RVALID  (s00_axi_rvalid),
        .S_AXI_RREADY  (s00_axi_rready),
        .instr_ready_ext  (instr_ready_w),
        .stream_ready_ext (dma_stream_ready),
        .slv_reg0_out  (slv_reg0_bus),
        .slv_reg3_out  (slv_reg3_bus),
        .slv_reg4_out  (slv_reg4_bus),
        .slv_reg5_out  (slv_reg5_bus),
        .slv_reg6_out  (slv_reg6_bus),
        .doorbell_out  (doorbell),
        .doorbell_clear(doorbell_clear)
    );

    // =========================================================================
    // AXI-Stream slave (DMA write)
    // =========================================================================
    tpu_slave_axi_stream #(
        .C_S_AXIS_TDATA_WIDTH(C_S00_AXIS_TDATA_WIDTH)
    ) tpu_slave_axi_stream_inst (
        .S_AXIS_ACLK        (s00_axis_aclk),
        .S_AXIS_ARESETN     (s00_axis_aresetn),
        .S_AXIS_TREADY      (s00_axis_tready),
        .S_AXIS_TDATA       (s00_axis_tdata),
        .S_AXIS_TSTRB       (s00_axis_tstrb),
        .S_AXIS_TLAST       (s00_axis_tlast),
        .S_AXIS_TVALID      (s00_axis_tvalid),
        .len                (dma_len),
        .data_to_bram       (dma_dram_din),
        .data_to_iram       (dma_iram_din),
        .write_pointer_stream(write_pointer),
        .done               (write_bram_done),
        .data_valid         (stream_data_valid),
        .write_en           (dma_data_write_en || dma_instr_write_en),
        .tpu_mode_stream    (latched_mode[2:0])
    );

    // =========================================================================
    // AXI-Stream master (DMA read)
    // =========================================================================
    tpu_master_axi_stream #(
        .C_M_AXIS_TDATA_WIDTH(C_M00_AXIS_TDATA_WIDTH),
        .C_M_START_COUNT     (C_M00_AXIS_START_COUNT)
    ) tpu_master_axi_stream_inst (
        .M_AXIS_ACLK    (m00_axis_aclk),
        .M_AXIS_ARESETN (m00_axis_aresetn),
        .M_AXIS_TVALID  (m00_axis_tvalid),
        .M_AXIS_TDATA   (m00_axis_tdata),
        .M_AXIS_TSTRB   (m00_axis_tstrb),
        .M_AXIS_TLAST   (m00_axis_tlast),
        .M_AXIS_TREADY  (m00_axis_tready),
        .data_to_ddr    (devmem_rd_data),
        .len            (dma_len),
        .read_en        (dma_start_stream),
        .done           (read_bram_done),
        .read_pointer_stream(read_pointer)
    );

    // =========================================================================
    // DMA engine sub-FSM (modes 1/2/4/5/6)
    // =========================================================================
    dma_engine u_dma_engine (
        .clk            (s00_axi_aclk),
        .rst_n          (s00_axi_aresetn),
        .start          (dma_start),
        .mode           (tpu_mode),
        .addr_ram_in    (addr_ram[7:0]),
        .write_pointer  (write_pointer),
        .done           (dma_done),
        .stream_ready   (dma_stream_ready),
        .data_write_en  (dma_data_write_en),
        .instr_write_en (dma_instr_write_en),
        .start_stream   (dma_start_stream),
        .read_en        (dma_read_en),
        .iram_addr      (dma_iram_addr),
        .write_bram_done(write_bram_done),
        .read_bram_done (read_bram_done),
        .start_dm_to_l2 (dma_start_dm_to_l2),
        .start_l2_to_dm (dma_start_l2_to_dm),
        .xfer_l2_done   (xfer_l2_done)
    );

    // =========================================================================
    // Compute ctrl sub-FSM (mode 3)
    // =========================================================================
    compute_ctrl u_compute_ctrl (
        .clk               (s00_axi_aclk),
        .rst_n             (s00_axi_aresetn),
        .start             (compute_start),
        .done              (compute_done),
        .start_compute_tile(cc_start_compute_tile),
        .compute_tile_done (compute_tile_done)
    );

    // =========================================================================
    // L2 ctrl sub-FSM (modes 7/8)
    // =========================================================================
    l2_ctrl u_l2_ctrl (
        .clk             (s00_axi_aclk),
        .rst_n           (s00_axi_aresetn),
        .start           (l2_start),
        .mode            (tpu_mode),
        .addr_l2_in      (addr_l2),
        .length_in       (dma_len),
        .done            (l2_done),
        // L2 tile Port A
        .l2_ct_addr      (lc_l2_ct_addr),
        .l2_ct_en        (lc_l2_ct_en),
        .l2_ct_we        (lc_l2_ct_we),
        .l2_ct_din       (lc_l2_ct_din),
        .l2_ct_dout      (lc_l2_ct_dout),
        // L1 DMA port
        .l1_dma_wr_en    (lc_l1_dma_wr_en),
        .l1_dma_wr_data  (lc_l1_dma_wr_data),
        .l1_dma_write_ptr(lc_l1_dma_write_ptr),
        .l1_dma_rd_en    (lc_l1_dma_rd_en),
        .l1_dma_rd_data  (lc_l1_dma_rd_data),
        .l1_dma_read_ptr (lc_l1_dma_read_ptr)
    );

    // =========================================================================
    // Device Memory (host DMA target, modes 1/2)
    // =========================================================================
    device_mem #(
        .ADDR_WIDTH(16),
        .DATA_WIDTH(32)
    ) u_device_mem (
        .clk(s00_axi_aclk),
        .rst_n(s00_axi_aresetn),
        // Port A — host DMA (dma_engine controls enable signals)
        .base_addr          (addr_devmem),
        .dma_wr_en          (dma_data_write_en && stream_data_valid),
        .dma_wr_data        (dma_dram_din),
        .dma_write_pointer  (write_pointer),
        .dma_rd_en          (dma_read_en),
        .dma_rd_data        (devmem_rd_data),
        .dma_read_pointer   (read_pointer),
        // Port B — L2 tile DevMem FSM
        .l2_addr_b          (dm_l2_addr),
        .l2_din_b           (dm_l2_din),
        .l2_dout_b          (dm_l2_dout),
        .l2_en_b            (dm_l2_en),
        .l2_we_b            (dm_l2_we)
    );

    // =========================================================================
    // L2 Tile (shared SRAM + tma_engine)
    // =========================================================================
    l2_tile #(
        .L2_ADDR_WIDTH(15),
        .DATA_WIDTH(32),
        .DM_ADDR_WIDTH(16)
    ) u_l2_tile (
        .clk(s00_axi_aclk),
        .rst_n(s00_axi_aresetn),
        // Port A — l2_ctrl side (L2↔L1 block copies)
        .ct_addr_a      (lc_l2_ct_addr),
        .ct_din_a       (lc_l2_ct_din),
        .ct_dout_a      (lc_l2_ct_dout),
        .ct_en_a        (lc_l2_ct_en),
        .ct_we_a        (lc_l2_ct_we),
        // Port B — device memory side (tma_engine inside l2_tile)
        .dm_addr        (dm_l2_addr),
        .dm_din         (dm_l2_din),
        .dm_dout        (dm_l2_dout),
        .dm_en          (dm_l2_en),
        .dm_we          (dm_l2_we),
        // Host-controlled DevMem↔L2 transfer (dma_engine triggers, modes 5/6)
        .start_dm_to_l2 (dma_start_dm_to_l2),
        .start_l2_to_dm (dma_start_l2_to_dm),
        .xfer_dm_base   (addr_devmem),
        .xfer_l2_base   (addr_l2),
        .xfer_len       (dma_len[15:0]),
        .xfer_done      (xfer_l2_done),
        // TMA instruction port (tensorcore → l2_tile)
        .tma_req        (ct_tma_req),
        .tma_dir        (ct_tma_dir),
        .tma_dm_base    (ct_tma_dm_base),
        .tma_l2_base    (ct_tma_l2_base),
        .tma_len        (ct_tma_len),
        .tma_done       (l2_tma_done)
    );

    // =========================================================================
    // Compute Tile
    // =========================================================================
    compute_tile #(
        .ADDR_WIDTH(13),
        .DATA_WIDTH(32)
    ) u_compute_tile (
        .clk(s00_axi_aclk),
        .rst_n(s00_axi_aresetn),
        // Control (from compute_ctrl sub-FSM)
        .start          (cc_start_compute_tile),
        .done           (compute_tile_done),
        // DMA Instruction (from dma_engine, mode 4)
        .instr_write_en (dma_instr_write_en && write_pointer[0]),
        .iram_addr      (dma_iram_addr),
        .dma_iram_din   (dma_iram_din),
        // DMA Data — L1 Port A (from l2_ctrl, modes 7/8)
        .base_addr      (addr_ram),
        .dma_wr_en      (lc_l1_dma_wr_en),
        .dma_wr_data    (lc_l1_dma_wr_data),
        .dma_write_pointer(lc_l1_dma_write_ptr),
        .dma_rd_en      (lc_l1_dma_rd_en),
        .dma_rd_data    (lc_l1_dma_rd_data),
        .dma_read_pointer(lc_l1_dma_read_ptr),
        // TMA signals (tensorcore → l2_tile)
        .tma_req        (ct_tma_req),
        .tma_dir        (ct_tma_dir),
        .tma_dm_base    (ct_tma_dm_base),
        .tma_l2_base    (ct_tma_l2_base),
        .tma_len        (ct_tma_len),
        .tma_done       (l2_tma_done)
    );

endmodule
