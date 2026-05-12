`timescale 1 ns / 1 ps
// ============================================================================
// mem_top.sv — Memory Subsystem Top-Level
//
// Simplified TPU top-level with only the memory hierarchy:
//   Host (PS) ↔ System Memory (BRAM) ↔ On-Chip Memory (BRAM)
//
// Interfaces:
//   - AXI-Lite slave  (s00_axi)  : control registers + doorbell
//   - AXI-Stream slave (s00_axis): DMA write path (host → sys_mem)
//   - AXI-Stream master(m00_axis): DMA read path  (sys_mem → host)
//   - AXI4-Full slave  (s01_axi) : direct MMIO read/write to sys_mem
//
// Modes (doorbell-driven via AXI-Lite reg0):
//   1 = DMA Write  : Host → System Memory
//   2 = DMA Read   : System Memory → Host
//   5 = SYS_TO_OC  : System Memory → On-Chip Memory
//   6 = OC_TO_SYS  : On-Chip Memory → System Memory
//
// AXI4-Full (s01_axi) provides direct MMIO to sys_mem (no doorbell needed).
// ============================================================================

module mem_top #(
    parameter integer C_S00_AXI_DATA_WIDTH  = 32,
    parameter integer C_S00_AXI_ADDR_WIDTH  = 6,
    parameter integer C_S00_AXIS_TDATA_WIDTH = 256,
    parameter integer C_M00_AXIS_TDATA_WIDTH = 256,
    parameter integer C_S01_AXI_DATA_WIDTH  = 32,
    parameter integer C_S01_AXI_ADDR_WIDTH  = 18
)(
    // ── AXI-Lite Slave (control registers) ──────────────────────────
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

    // ── AXI-Stream Slave (DMA write path) ───────────────────────────
    input  wire        s00_axis_aclk,
    input  wire        s00_axis_aresetn,
    output wire        s00_axis_tready,
    input  wire [C_S00_AXIS_TDATA_WIDTH-1:0] s00_axis_tdata,
    input  wire [(C_S00_AXIS_TDATA_WIDTH/8)-1:0] s00_axis_tstrb,
    input  wire        s00_axis_tlast,
    input  wire        s00_axis_tvalid,

    // ── AXI-Stream Master (DMA read path) ───────────────────────────
    input  wire        m00_axis_aclk,
    input  wire        m00_axis_aresetn,
    output wire        m00_axis_tvalid,
    output wire [C_M00_AXIS_TDATA_WIDTH-1:0] m00_axis_tdata,
    output wire [(C_M00_AXIS_TDATA_WIDTH/8)-1:0] m00_axis_tstrb,
    output wire [(C_M00_AXIS_TDATA_WIDTH/8)-1:0] m00_axis_tkeep,
    output wire        m00_axis_tlast,
    input  wire        m00_axis_tready,

    // ── AXI4-Full Slave (MMIO direct access to sys_mem) ─────────────
    input  wire        s01_axi_aclk,
    input  wire        s01_axi_aresetn,
    input  wire [C_S01_AXI_ADDR_WIDTH-1:0] s01_axi_awaddr,
    input  wire [7:0]  s01_axi_awlen,
    input  wire [2:0]  s01_axi_awsize,
    input  wire [1:0]  s01_axi_awburst,
    input  wire        s01_axi_awvalid,
    output wire        s01_axi_awready,
    input  wire [C_S01_AXI_DATA_WIDTH-1:0] s01_axi_wdata,
    input  wire [(C_S01_AXI_DATA_WIDTH/8)-1:0] s01_axi_wstrb,
    input  wire        s01_axi_wlast,
    input  wire        s01_axi_wvalid,
    output wire        s01_axi_wready,
    output wire [1:0]  s01_axi_bresp,
    output wire        s01_axi_bvalid,
    input  wire        s01_axi_bready,
    input  wire [C_S01_AXI_ADDR_WIDTH-1:0] s01_axi_araddr,
    input  wire [7:0]  s01_axi_arlen,
    input  wire [2:0]  s01_axi_arsize,
    input  wire [1:0]  s01_axi_arburst,
    input  wire        s01_axi_arvalid,
    output wire        s01_axi_arready,
    output wire [C_S01_AXI_DATA_WIDTH-1:0] s01_axi_rdata,
    output wire [1:0]  s01_axi_rresp,
    output wire        s01_axi_rlast,
    output wire        s01_axi_rvalid,
    input  wire        s01_axi_rready
);

    // =========================================================================
    // AXI-Lite register buses
    // =========================================================================
    wire [31:0] slv_reg0_bus;
    wire [31:0] slv_reg1_bus;
    wire [31:0] slv_reg2_bus;
    wire [31:0] slv_reg3_bus;
    wire [31:0] slv_reg4_bus;
    wire [31:0] slv_reg5_bus;
    wire [31:0] slv_reg6_bus;
    wire [31:0] slv_reg7_bus;
    
    wire [31:0] debug_master_bus = 32'd0;

    wire [15:0] addr_sys    = slv_reg3_bus[15:0];
    wire [14:0] addr_onchip = slv_reg4_bus[14:0];
    wire [31:0] xfer_len    = slv_reg6_bus;

    wire [3:0]  tpu_mode    = slv_reg0_bus[3:0];

    // Doorbell mechanism
    wire        doorbell;
    reg         doorbell_clear;

    // Mode constants
    localparam MODE_IDLE      = 4'd0;
    localparam MODE_DMA_WRITE = 4'd1;
    localparam MODE_DMA_READ  = 4'd2;
    localparam MODE_SYS_TO_OC = 4'd5;
    localparam MODE_OC_TO_SYS = 4'd6;

    // =========================================================================
    // FSM state tracking
    // =========================================================================
    reg        fsm_running;
    reg        fsm_start;
    wire       fsm_done;

    wire instr_ready_w = !fsm_running;

    // =========================================================================
    // mem_ctrl wires
    // =========================================================================
    wire       mc_stream_ready;
    wire       mc_data_write_en;
    wire       mc_start_stream;
    wire       mc_read_en;

    // mem_ctrl ↔ sys_mem scalar port
    wire [15:0] mc_sys_scalar_addr;
    wire [31:0] mc_sys_scalar_din;
    wire [31:0] mc_sys_scalar_dout;
    wire        mc_sys_scalar_en;
    wire        mc_sys_scalar_we;

    // mem_ctrl ↔ onchip_mem Port A
    wire [14:0] mc_oc_addr;
    wire [31:0] mc_oc_din;
    wire [31:0] mc_oc_dout;
    wire        mc_oc_en;
    wire        mc_oc_we;

    // =========================================================================
    // AXI-Full ↔ sys_mem scalar port
    // =========================================================================
    wire [15:0] af_mem_addr;
    wire [31:0] af_mem_din;
    wire [31:0] af_mem_dout;
    wire        af_mem_en;
    wire        af_mem_we;

    // =========================================================================
    // Muxed sys_mem scalar port (mem_ctrl vs AXI-Full)
    // mem_ctrl gets priority when FSM is running modes 5/6
    // =========================================================================
    wire        mc_owns_scalar = fsm_running &&
                                 (tpu_mode == MODE_SYS_TO_OC || tpu_mode == MODE_OC_TO_SYS);

    wire [15:0] muxed_scalar_addr = mc_owns_scalar ? mc_sys_scalar_addr : af_mem_addr;
    wire [31:0] muxed_scalar_din  = mc_owns_scalar ? mc_sys_scalar_din  : af_mem_din;
    wire        muxed_scalar_en   = mc_owns_scalar ? mc_sys_scalar_en   : af_mem_en;
    wire        muxed_scalar_we   = mc_owns_scalar ? mc_sys_scalar_we   : af_mem_we;

    // sys_mem scalar readback goes to both consumers
    assign mc_sys_scalar_dout = af_mem_dout; // same wire from sys_mem Port B
    // af_mem_dout is wired directly from sys_mem

    // =========================================================================
    // AXI-Stream plumbing wires
    // =========================================================================
    wire [15:0]  write_pointer;
    wire [15:0]  read_pointer;
    wire [255:0] dma_wr_data;
    wire [63:0]  dma_iram_din;  // unused but stream module needs it
    wire         stream_data_valid;
    wire         write_bram_done;
    wire         read_bram_done;
    wire [255:0] sys_rd_data;

    // =========================================================================
    // Arbiter FSM (single-channel, simplified)
    // =========================================================================
    reg [3:0] latched_mode;

    always @(posedge s00_axi_aclk or negedge s00_axi_aresetn) begin
        if (!s00_axi_aresetn) begin
            fsm_running    <= 1'b0;
            fsm_start      <= 1'b0;
            doorbell_clear <= 1'b0;
            latched_mode   <= 4'd0;
        end else begin
            fsm_start      <= 1'b0;
            doorbell_clear <= 1'b0;

            if (fsm_done) fsm_running <= 1'b0;

            if (doorbell) begin
                doorbell_clear <= 1'b1;
                latched_mode   <= tpu_mode;

                case (tpu_mode)
                    MODE_DMA_WRITE,
                    MODE_DMA_READ,
                    MODE_SYS_TO_OC,
                    MODE_OC_TO_SYS: begin
                        if (!fsm_running || fsm_done) begin
                            fsm_running <= 1'b1;
                            fsm_start   <= 1'b1;
                        end
                    end
                    default: ; // unknown mode — doorbell cleared, nothing started
                endcase
            end
        end
    end

    // =========================================================================
    // AXI-Lite Slave (control registers)
    // =========================================================================
    tpu_slave_axi_lite #(
        .C_S_AXI_DATA_WIDTH(C_S00_AXI_DATA_WIDTH),
        .C_S_AXI_ADDR_WIDTH(C_S00_AXI_ADDR_WIDTH)
    ) u_axi_lite (
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
        .stream_ready_ext (mc_stream_ready),
        .slv_reg0_out  (slv_reg0_bus),
        .slv_reg3_out  (slv_reg3_bus),
        .slv_reg4_out  (slv_reg4_bus),
        .slv_reg5_out  (slv_reg5_bus),
        .slv_reg5_in   (debug_master_bus),
        .slv_reg6_out  (slv_reg6_bus),
        .doorbell_out  (doorbell),
        .doorbell_clear(doorbell_clear)
    );

    // =========================================================================
    // AXI-Stream Slave (DMA write)
    // =========================================================================
    wire [31:0] stream_len = {3'b000, xfer_len[31:3]}; // num 256-bit beats
    tpu_slave_axi_stream #(
        .C_S_AXIS_TDATA_WIDTH(C_S00_AXIS_TDATA_WIDTH)
    ) u_stream_slave (
        .S_AXIS_ACLK        (s00_axis_aclk),
        .S_AXIS_ARESETN     (s00_axis_aresetn),
        .S_AXIS_TREADY      (s00_axis_tready),
        .S_AXIS_TDATA       (s00_axis_tdata),
        .S_AXIS_TSTRB       (s00_axis_tstrb),
        .S_AXIS_TLAST       (s00_axis_tlast),
        .S_AXIS_TVALID      (s00_axis_tvalid),
        .len                (stream_len),
        .data_to_bram       (dma_wr_data),
        .data_to_iram       (dma_iram_din),
        .write_pointer_stream(write_pointer),
        .done               (write_bram_done),
        .data_valid         (stream_data_valid),
        .write_en           (mc_data_write_en),
        .tpu_mode_stream    (latched_mode[2:0])
    );

    // =========================================================================
    // AXI-Stream Master (DMA read)
    // =========================================================================
    tpu_master_axi_stream #(
        .C_M_AXIS_TDATA_WIDTH(C_M00_AXIS_TDATA_WIDTH)
    ) u_stream_master (
        .M_AXIS_ACLK    (m00_axis_aclk),
        .M_AXIS_ARESETN (m00_axis_aresetn),
        .M_AXIS_TVALID  (m00_axis_tvalid),
        .M_AXIS_TDATA   (m00_axis_tdata),
        .M_AXIS_TSTRB   (m00_axis_tstrb),
        .M_AXIS_TKEEP   (m00_axis_tkeep),
        .M_AXIS_TLAST   (m00_axis_tlast),
        .M_AXIS_TREADY  (m00_axis_tready),
        .data_to_ddr    (sys_rd_data),
        .len            (stream_len),
        .read_en        (mc_read_en),
        .done           (read_bram_done),
        // .debug_master   (debug_master_bus),
        .read_pointer_stream(read_pointer)
    );

    // =========================================================================
    // AXI4-Full Slave (direct MMIO to sys_mem)
    // =========================================================================
    axi_full_slave #(
        .C_S_AXI_DATA_WIDTH(C_S01_AXI_DATA_WIDTH),
        .C_S_AXI_ADDR_WIDTH(C_S01_AXI_ADDR_WIDTH)
    ) u_axi_full (
        .S_AXI_ACLK    (s01_axi_aclk),
        .S_AXI_ARESETN (s01_axi_aresetn),
        .S_AXI_AWADDR  (s01_axi_awaddr),
        .S_AXI_AWLEN   (s01_axi_awlen),
        .S_AXI_AWSIZE  (s01_axi_awsize),
        .S_AXI_AWBURST (s01_axi_awburst),
        .S_AXI_AWVALID (s01_axi_awvalid),
        .S_AXI_AWREADY (s01_axi_awready),
        .S_AXI_WDATA   (s01_axi_wdata),
        .S_AXI_WSTRB   (s01_axi_wstrb),
        .S_AXI_WLAST   (s01_axi_wlast),
        .S_AXI_WVALID  (s01_axi_wvalid),
        .S_AXI_WREADY  (s01_axi_wready),
        .S_AXI_BRESP   (s01_axi_bresp),
        .S_AXI_BVALID  (s01_axi_bvalid),
        .S_AXI_BREADY  (s01_axi_bready),
        .S_AXI_ARADDR  (s01_axi_araddr),
        .S_AXI_ARLEN   (s01_axi_arlen),
        .S_AXI_ARSIZE  (s01_axi_arsize),
        .S_AXI_ARBURST (s01_axi_arburst),
        .S_AXI_ARVALID (s01_axi_arvalid),
        .S_AXI_ARREADY (s01_axi_arready),
        .S_AXI_RDATA   (s01_axi_rdata),
        .S_AXI_RRESP   (s01_axi_rresp),
        .S_AXI_RLAST   (s01_axi_rlast),
        .S_AXI_RVALID  (s01_axi_rvalid),
        .S_AXI_RREADY  (s01_axi_rready),
        .mem_addr       (af_mem_addr),
        .mem_din        (af_mem_din),
        .mem_dout       (af_mem_dout),
        .mem_en         (af_mem_en),
        .mem_we         (af_mem_we)
    );

    // =========================================================================
    // Memory Controller FSM
    // =========================================================================
    mem_ctrl u_mem_ctrl (
        .clk             (s00_axi_aclk),
        .rst_n           (s00_axi_aresetn),
        .start           (fsm_start),
        .mode            (tpu_mode),
        .done            (fsm_done),
        .addr_sys_in     (addr_sys),
        .addr_oc_in      (addr_onchip),
        .length_in       (xfer_len),
        .stream_ready    (mc_stream_ready),
        .write_pointer   (write_pointer),
        .data_write_en   (mc_data_write_en),
        .start_stream    (mc_start_stream),
        .read_en         (mc_read_en),
        .write_bram_done (write_bram_done),
        .read_bram_done  (read_bram_done),
        // sys_mem scalar port (muxed with AXI-Full in this module)
        .sys_scalar_addr (mc_sys_scalar_addr),
        .sys_scalar_din  (mc_sys_scalar_din),
        .sys_scalar_dout (mc_sys_scalar_dout),
        .sys_scalar_en   (mc_sys_scalar_en),
        .sys_scalar_we   (mc_sys_scalar_we),
        // on-chip memory Port A
        .oc_addr         (mc_oc_addr),
        .oc_din          (mc_oc_din),
        .oc_dout         (mc_oc_dout),
        .oc_en           (mc_oc_en),
        .oc_we           (mc_oc_we)
    );

    // =========================================================================
    // Device Memory Emulation Layer
    // =========================================================================
    device_mem #(
        .ADDR_WIDTH(16),
        .DATA_WIDTH(256)
    ) u_device_mem (
        .clk             (s00_axi_aclk),
        .rst_n           (s00_axi_aresetn),
        // Port A — DMA
        .base_addr       (addr_sys[15:3]),
        .dma_wr_en       (mc_data_write_en && stream_data_valid),
        .dma_wr_data     (dma_wr_data),
        .dma_write_pointer({3'b000, write_pointer}),
        .dma_rd_en       (mc_read_en),
        .dma_rd_data     (sys_rd_data),
        .dma_read_pointer({3'b000, read_pointer}),
        // Port B — Scalar (muxed: mem_ctrl or AXI-Full)
        .l2_addr_b       (muxed_scalar_addr),
        .l2_din_b        (muxed_scalar_din),
        .l2_dout_b       (af_mem_dout),  // read data goes to both consumers
        .l2_en_b         (muxed_scalar_en),
        .l2_we_b         (muxed_scalar_we)
    );

    // =========================================================================
    // On-Chip Memory
    // =========================================================================
    onchip_mem #(
        .ADDR_WIDTH(15),
        .DATA_WIDTH(32)
    ) u_onchip_mem (
        .clk   (s00_axi_aclk),
        .rst_n (s00_axi_aresetn),
        // Port A — mem_ctrl
        .addr_a(mc_oc_addr),
        .din_a (mc_oc_din),
        .dout_a(mc_oc_dout),
        .en_a  (mc_oc_en),
        .we_a  (mc_oc_we),
        // Port B — reserved (compute tile stub)
        .addr_b(15'd0),
        .din_b (32'd0),
        .dout_b(),
        .en_b  (1'b0),
        .we_b  (1'b0)
    );

endmodule
