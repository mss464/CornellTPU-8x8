`timescale 1 ns / 1 ps

	module tpu #
	(
		// Parameters of Axi Slave Bus Interface S00_AXI
		parameter integer C_S00_AXI_DATA_WIDTH	= 32,
		parameter integer C_S00_AXI_ADDR_WIDTH	= 6,

		// Parameters of Axi Slave Bus Interface S00_AXIS
		parameter integer C_S00_AXIS_TDATA_WIDTH	= 32,

		// Parameters of Axi Master Bus Interface M00_AXIS
		parameter integer C_M00_AXIS_TDATA_WIDTH	= 32,
		parameter integer C_M00_AXIS_START_COUNT	= 32
	)
	(
		// Ports of Axi Slave Bus Interface S00_AXI
		input wire  s00_axi_aclk,
		input wire  s00_axi_aresetn,
		input wire [C_S00_AXI_ADDR_WIDTH-1 : 0] s00_axi_awaddr,
		input wire [2 : 0] s00_axi_awprot,
		input wire  s00_axi_awvalid,
		output wire  s00_axi_awready,
		input wire [C_S00_AXI_DATA_WIDTH-1 : 0] s00_axi_wdata,
		input wire [(C_S00_AXI_DATA_WIDTH/8)-1 : 0] s00_axi_wstrb,
		input wire  s00_axi_wvalid,
		output wire  s00_axi_wready,
		output wire [1 : 0] s00_axi_bresp,
		output wire  s00_axi_bvalid,
		input wire  s00_axi_bready,
		input wire [C_S00_AXI_ADDR_WIDTH-1 : 0] s00_axi_araddr,
		input wire [2 : 0] s00_axi_arprot,
		input wire  s00_axi_arvalid,
		output wire  s00_axi_arready,
		output wire [C_S00_AXI_DATA_WIDTH-1 : 0] s00_axi_rdata,
		output wire [1 : 0] s00_axi_rresp,
		output wire  s00_axi_rvalid,
		input wire  s00_axi_rready,

		// Ports of Axi Slave Bus Interface S00_AXIS
		input wire  s00_axis_aclk,
		input wire  s00_axis_aresetn,
		output wire  s00_axis_tready,
		input wire [C_S00_AXIS_TDATA_WIDTH-1 : 0] s00_axis_tdata,
		input wire [(C_S00_AXIS_TDATA_WIDTH/8)-1 : 0] s00_axis_tstrb,
		input wire  s00_axis_tlast,
		input wire  s00_axis_tvalid,

		// Ports of Axi Master Bus Interface M00_AXIS
		input wire  m00_axis_aclk,
		input wire  m00_axis_aresetn,
		output wire  m00_axis_tvalid,
		output wire [C_M00_AXIS_TDATA_WIDTH-1 : 0] m00_axis_tdata,
		output wire [(C_M00_AXIS_TDATA_WIDTH/8)-1 : 0] m00_axis_tstrb,
		output wire  m00_axis_tlast,
		input wire  m00_axis_tready
	);

    // =========================================================================
    // AXI-Lite register buses
    // =========================================================================
    wire [31:0] slv_reg0_bus;
    wire [31:0] slv_reg3_bus;
    wire [31:0] slv_reg4_bus;
    wire [31:0] slv_reg5_bus;
    wire [31:0] slv_reg6_bus;

    reg         instr_ready;
    reg         stream_ready;
    wire [12:0] addr_ram    = slv_reg3_bus[12:0]; // L1 / IRAM base address
    wire [15:0] addr_devmem = slv_reg4_bus[15:0]; // device memory base address
    wire [14:0] addr_l2     = slv_reg5_bus[14:0]; // L2 SRAM base address
    wire [31:0] dma_len     = slv_reg6_bus;        // transfer length in words

    wire [3:0] tpu_mode = slv_reg0_bus[3:0]; // 4-bit mode field

    // Mode constants
    localparam MODE_IDLE      = 4'd0;
    localparam MODE_WR_DEVMEM = 4'd1;  // host → device memory (AXI-Stream)
    localparam MODE_RD_DEVMEM = 4'd2;  // device memory → host (AXI-Stream)
    localparam MODE_COMPUTE   = 4'd3;  // execute IRAM instructions
    localparam MODE_WR_IRAM   = 4'd4;  // host → IRAM (AXI-Stream)
    localparam MODE_DM2L2     = 4'd5;  // device memory → L2 block copy
    localparam MODE_L22DM     = 4'd6;  // L2 → device memory block copy
    localparam MODE_L22L1     = 4'd7;  // L2 → compute tile L1 block copy
    localparam MODE_L12L2     = 4'd8;  // compute tile L1 → L2 block copy

    // FSM state encoding
    localparam ST_IDLE         = 4'd0;
    localparam ST_EXEC_WRITE   = 4'd1;
    localparam ST_EXEC_READ    = 4'd2;
    localparam ST_EXEC_COMPUTE = 4'd3;
    localparam ST_EXEC_DM2L2   = 4'd4;
    localparam ST_EXEC_L22DM   = 4'd5;
    localparam ST_EXEC_L22L1   = 4'd6;
    localparam ST_EXEC_L12L2   = 4'd7;
    localparam ST_WAIT_DONE    = 4'd8;

    reg [3:0] state = ST_IDLE;

    // =========================================================================
    // Control signals
    // =========================================================================
    reg start_compute_tile;
    wire compute_tile_done;

    // Host DMA (modes 1/2/4) — AXI-Stream interface
    reg  data_write_en, instr_write_en, read_en, start_stream;
    wire write_bram_done, read_bram_done;
    wire [15:0] write_pointer;
    wire [15:0] read_pointer;
    wire [31:0] dma_dram_din;
    wire [63:0] dma_iram_din;
    wire [31:0] dma_dout;

    // L2 tile DevMem FSM control (modes 5/6)
    reg  start_dm_to_l2, start_l2_to_dm;
    wire xfer_l2_done;

    // L2↔L1 burst transfer state (modes 7/8, managed by tpu.sv FSM)
    reg [15:0] l2l1_rd_issued; // number of reads issued this transfer
    reg        l2l1_rd_valid;  // data from the previous read is valid this cycle
    reg [15:0] l2l1_wr_ptr;   // write address offset (1 cycle behind rd_issued)

    // L2 tile Port A (compute-tile-side) — combinational wires
    wire [14:0] l2_ct_addr; // address driven into l2_tile Port A
    wire        l2_ct_en;
    wire        l2_ct_we;
    wire [31:0] l2_ct_din;  // data written to L2 (from L1 read, L1→L2 mode)
    wire [31:0] l2_ct_dout; // data read from L2 (to L1 write, L2→L1 mode)

    // TMA signals — compute_tile (tensorcore) → l2_tile
    wire        ct_tma_req;
    wire        ct_tma_dir;
    wire [15:0] ct_tma_dm_base;
    wire [14:0] ct_tma_l2_base;
    wire [15:0] ct_tma_len;
    wire        l2_tma_done;

    // Device memory Port B (driven by l2_tile)
    wire [15:0] dm_l2_addr;
    wire [31:0] dm_l2_din;
    wire [31:0] dm_l2_dout;
    wire        dm_l2_en;
    wire        dm_l2_we;

    // L1 DMA interface — used for L2↔L1 transfers (combinational wires)
    wire        l1_dma_wr_en;
    wire [31:0] l1_dma_wr_data;
    wire [15:0] l1_dma_write_ptr;
    wire        l1_dma_rd_en;
    wire [31:0] l1_dma_rd_data;   // output from compute_tile
    wire [15:0] l1_dma_read_ptr;

    // IRAM address counter
    reg [7:0] iram_addr;

    // =========================================================================
    // L2↔L1 combinational port driving
    // =========================================================================
    // L2 Port A: driven from state and counters.
    // Mode L22L1: read L2 at addr_l2+rd_issued, write L1 when rd_valid is set.
    // Mode L12L2: read L1, write L2 at addr_l2+wr_ptr when rd_valid is set.
    assign l2_ct_addr = (state == ST_EXEC_L22L1) ? (addr_l2 + l2l1_rd_issued[14:0]) :
                        (state == ST_EXEC_L12L2) ? (addr_l2 + l2l1_wr_ptr[14:0])    : 15'b0;

    assign l2_ct_en   = (state == ST_EXEC_L22L1 && l2l1_rd_issued < dma_len[15:0]) ||
                        (state == ST_EXEC_L12L2  && l2l1_rd_valid);

    assign l2_ct_we   = (state == ST_EXEC_L12L2 && l2l1_rd_valid);

    assign l2_ct_din  = l1_dma_rd_data; // L1 read data → L2 write data

    // L1 DMA: driven from state and counters.
    assign l1_dma_wr_en      = (state == ST_EXEC_L22L1 && l2l1_rd_valid);
    assign l1_dma_wr_data    = l2_ct_dout; // L2 read data → L1 write data
    assign l1_dma_write_ptr  = l2l1_wr_ptr;

    assign l1_dma_rd_en      = (state == ST_EXEC_L12L2 && l2l1_rd_issued < dma_len[15:0]);
    assign l1_dma_read_ptr   = {3'b0, l2l1_rd_issued[12:0]}; // 16-bit pointer, 13-bit L1 addr

    // =========================================================================
    // AXI-Lite slave instantiation
    // =========================================================================
    tpu_slave_axi_lite # (
        .C_S_AXI_DATA_WIDTH(C_S00_AXI_DATA_WIDTH),
        .C_S_AXI_ADDR_WIDTH(C_S00_AXI_ADDR_WIDTH)
    ) tpu_slave_axi_lite_inst (
        .S_AXI_ACLK(s00_axi_aclk),
        .S_AXI_ARESETN(s00_axi_aresetn),
        .S_AXI_AWADDR(s00_axi_awaddr),
        .S_AXI_AWPROT(s00_axi_awprot),
        .S_AXI_AWVALID(s00_axi_awvalid),
        .S_AXI_AWREADY(s00_axi_awready),
        .S_AXI_WDATA(s00_axi_wdata),
        .S_AXI_WSTRB(s00_axi_wstrb),
        .S_AXI_WVALID(s00_axi_wvalid),
        .S_AXI_WREADY(s00_axi_wready),
        .S_AXI_BRESP(s00_axi_bresp),
        .S_AXI_BVALID(s00_axi_bvalid),
        .S_AXI_BREADY(s00_axi_bready),
        .S_AXI_ARADDR(s00_axi_araddr),
        .S_AXI_ARPROT(s00_axi_arprot),
        .S_AXI_ARVALID(s00_axi_arvalid),
        .S_AXI_ARREADY(s00_axi_arready),
        .S_AXI_RDATA(s00_axi_rdata),
        .S_AXI_RRESP(s00_axi_rresp),
        .S_AXI_RVALID(s00_axi_rvalid),
        .S_AXI_RREADY(s00_axi_rready),
        .instr_ready_ext(instr_ready),
        .stream_ready_ext(stream_ready),
        .slv_reg0_out(slv_reg0_bus),
        .slv_reg3_out(slv_reg3_bus),
        .slv_reg4_out(slv_reg4_bus),
        .slv_reg5_out(slv_reg5_bus),
        .slv_reg6_out(slv_reg6_bus)
    );

    // =========================================================================
    // AXI-Stream slave (DMA write)
    // =========================================================================
    tpu_slave_axi_stream # (
        .C_S_AXIS_TDATA_WIDTH(C_S00_AXIS_TDATA_WIDTH)
    ) tpu_slave_axi_stream_inst (
        .S_AXIS_ACLK(s00_axis_aclk),
        .S_AXIS_ARESETN(s00_axis_aresetn),
        .S_AXIS_TREADY(s00_axis_tready),
        .S_AXIS_TDATA(s00_axis_tdata),
        .S_AXIS_TSTRB(s00_axis_tstrb),
        .S_AXIS_TLAST(s00_axis_tlast),
        .S_AXIS_TVALID(s00_axis_tvalid),
        .len(dma_len),
        .data_to_bram(dma_dram_din),
        .data_to_iram(dma_iram_din),
        .write_pointer_stream(write_pointer),
        .done(write_bram_done),
        .write_en(data_write_en || instr_write_en),
        .tpu_mode_stream(tpu_mode[2:0])
    );

    // =========================================================================
    // AXI-Stream master (DMA read)
    // =========================================================================
    wire [31:0] devmem_rd_data; // device_mem Port A read output

    tpu_master_axi_stream # (
        .C_M_AXIS_TDATA_WIDTH(C_M00_AXIS_TDATA_WIDTH),
        .C_M_START_COUNT(C_M00_AXIS_START_COUNT)
    ) tpu_master_axi_stream_inst (
        .M_AXIS_ACLK(m00_axis_aclk),
        .M_AXIS_ARESETN(m00_axis_aresetn),
        .M_AXIS_TVALID(m00_axis_tvalid),
        .M_AXIS_TDATA(m00_axis_tdata),
        .M_AXIS_TSTRB(m00_axis_tstrb),
        .M_AXIS_TLAST(m00_axis_tlast),
        .M_AXIS_TREADY(m00_axis_tready),
        .data_to_ddr(devmem_rd_data),
        .len(dma_len),
        .read_en(start_stream),
        .done(read_bram_done),
        .read_pointer_stream(read_pointer)
    );

    // =========================================================================
    // IRAM address counter
    // =========================================================================
    always @(posedge s00_axi_aclk or negedge s00_axi_aresetn) begin
        if (!s00_axi_aresetn) begin
            iram_addr <= 0;
        end else if (instr_write_en && write_pointer[0]) begin
            iram_addr <= addr_ram[7:0] + write_pointer[7:1];
        end
    end

    // =========================================================================
    // Main FSM
    // =========================================================================
    always @(posedge s00_axi_aclk or negedge s00_axi_aresetn) begin
        if (!s00_axi_aresetn) begin
            state              <= ST_IDLE;
            instr_ready        <= 1'b1;
            stream_ready       <= 1'b1;
            data_write_en      <= 1'b0;
            instr_write_en     <= 1'b0;
            read_en            <= 1'b0;
            start_compute_tile <= 1'b0;
            start_stream       <= 1'b0;
            start_dm_to_l2     <= 1'b0;
            start_l2_to_dm     <= 1'b0;
            l2l1_rd_issued     <= 16'd0;
            l2l1_rd_valid      <= 1'b0;
            l2l1_wr_ptr        <= 16'd0;
        end else begin
            // Defaults — most control signals are pulses
            data_write_en      <= 1'b0;
            instr_write_en     <= 1'b0;
            read_en            <= 1'b0;
            start_compute_tile <= 1'b0;
            start_stream       <= 1'b0;
            start_dm_to_l2     <= 1'b0;
            start_l2_to_dm     <= 1'b0;
            l2l1_rd_valid      <= 1'b0;

            case (state)
                //--------------------------------------------------------------
                ST_IDLE: begin
                    instr_ready <= 1'b1;
                    case (tpu_mode)
                        MODE_WR_DEVMEM: begin
                            instr_ready   <= 1'b0;
                            data_write_en <= 1'b1;
                            stream_ready  <= 1'b1;
                            state         <= ST_EXEC_WRITE;
                        end
                        MODE_RD_DEVMEM: begin
                            instr_ready  <= 1'b0;
                            read_en      <= 1'b1;
                            start_stream <= 1'b1;
                            stream_ready <= 1'b1;
                            state        <= ST_EXEC_READ;
                        end
                        MODE_COMPUTE: begin
                            instr_ready        <= 1'b0;
                            start_compute_tile <= 1'b1;
                            stream_ready       <= 1'b0;
                            state              <= ST_EXEC_COMPUTE;
                        end
                        MODE_WR_IRAM: begin
                            instr_ready    <= 1'b0;
                            instr_write_en <= 1'b1;
                            stream_ready   <= 1'b1;
                            state          <= ST_EXEC_WRITE;
                        end
                        MODE_DM2L2: begin
                            instr_ready    <= 1'b0;
                            start_dm_to_l2 <= 1'b1;
                            state          <= ST_EXEC_DM2L2;
                        end
                        MODE_L22DM: begin
                            instr_ready    <= 1'b0;
                            start_l2_to_dm <= 1'b1;
                            state          <= ST_EXEC_L22DM;
                        end
                        MODE_L22L1: begin
                            instr_ready    <= 1'b0;
                            l2l1_rd_issued <= 16'd0;
                            l2l1_rd_valid  <= 1'b0;
                            state          <= ST_EXEC_L22L1;
                        end
                        MODE_L12L2: begin
                            instr_ready    <= 1'b0;
                            l2l1_rd_issued <= 16'd0;
                            l2l1_rd_valid  <= 1'b0;
                            state          <= ST_EXEC_L12L2;
                        end
                        default: ; // stay in IDLE
                    endcase
                end

                //--------------------------------------------------------------
                ST_EXEC_WRITE: begin
                    stream_ready <= 1'b1;
                    if (tpu_mode == MODE_WR_DEVMEM)
                        data_write_en <= 1'b1;
                    else if (tpu_mode == MODE_WR_IRAM)
                        instr_write_en <= 1'b1;
                    if (write_bram_done)
                        state <= ST_WAIT_DONE;
                end

                //--------------------------------------------------------------
                ST_EXEC_READ: begin
                    stream_ready <= 1'b1;
                    read_en <= 1'b1;
                    if (read_bram_done)
                        state <= ST_WAIT_DONE;
                end

                //--------------------------------------------------------------
                ST_EXEC_COMPUTE: begin
                    if (compute_tile_done)
                        state <= ST_WAIT_DONE;
                end

                //--------------------------------------------------------------
                // Wait for l2_tile's internal DevMem FSM to finish
                ST_EXEC_DM2L2: begin
                    if (xfer_l2_done)
                        state <= ST_WAIT_DONE;
                end

                ST_EXEC_L22DM: begin
                    if (xfer_l2_done)
                        state <= ST_WAIT_DONE;
                end

                //--------------------------------------------------------------
                // L2 → L1: issue reads from L2 Port A, write to L1 DMA port
                // Read address: addr_l2 + rd_issued  (combinational, 1-cycle BRAM latency)
                // Write (L1):   happens when rd_valid=1 (data valid from previous read)
                ST_EXEC_L22L1: begin
                    if (l2l1_rd_issued < dma_len[15:0]) begin
                        l2l1_rd_valid  <= 1'b1;
                        l2l1_wr_ptr    <= l2l1_rd_issued;
                        l2l1_rd_issued <= l2l1_rd_issued + 16'd1;
                    end
                    // Done: last write committed (rd_valid=1 and no more reads)
                    if (l2l1_rd_valid && l2l1_rd_issued >= dma_len[15:0])
                        state <= ST_WAIT_DONE;
                    else if (!l2l1_rd_valid && l2l1_rd_issued >= dma_len[15:0])
                        state <= ST_WAIT_DONE;
                end

                //--------------------------------------------------------------
                // L1 → L2: issue reads from L1 DMA port, write to L2 Port A
                // Read address: addr_ram + rd_issued  (through compute_tile L1 Port A)
                // Write (L2):   happens when rd_valid=1 (data valid from previous read)
                ST_EXEC_L12L2: begin
                    if (l2l1_rd_issued < dma_len[15:0]) begin
                        l2l1_rd_valid  <= 1'b1;
                        l2l1_wr_ptr    <= l2l1_rd_issued;
                        l2l1_rd_issued <= l2l1_rd_issued + 16'd1;
                    end
                    if (l2l1_rd_valid && l2l1_rd_issued >= dma_len[15:0])
                        state <= ST_WAIT_DONE;
                    else if (!l2l1_rd_valid && l2l1_rd_issued >= dma_len[15:0])
                        state <= ST_WAIT_DONE;
                end

                //--------------------------------------------------------------
                ST_WAIT_DONE: begin
                    instr_ready <= 1'b1;
                    if (tpu_mode == MODE_IDLE)
                        state <= ST_IDLE;
                end

                default: state <= ST_IDLE;
            endcase
        end
    end

    // =========================================================================
    // Submodule instantiations
    // =========================================================================

    // --- Device Memory (host DMA target, modes 1/2) ---
    device_mem #(
        .ADDR_WIDTH(16),
        .DATA_WIDTH(32)
    ) u_device_mem (
        .clk(s00_axi_aclk),
        .rst_n(s00_axi_aresetn),
        // Port A — host DMA
        .base_addr(addr_devmem),
        .dma_wr_en(data_write_en),
        .dma_wr_data(dma_dram_din),
        .dma_write_pointer(write_pointer),
        .dma_rd_en(read_en),
        .dma_rd_data(devmem_rd_data),
        .dma_read_pointer(read_pointer),
        // Port B — L2 tile DevMem FSM
        .l2_addr_b(dm_l2_addr),
        .l2_din_b(dm_l2_din),
        .l2_dout_b(dm_l2_dout),
        .l2_en_b(dm_l2_en),
        .l2_we_b(dm_l2_we)
    );

    // --- L2 Tile (shared SRAM + tma_engine) ---
    l2_tile #(
        .L2_ADDR_WIDTH(15),
        .DATA_WIDTH(32),
        .DM_ADDR_WIDTH(16)
    ) u_l2_tile (
        .clk(s00_axi_aclk),
        .rst_n(s00_axi_aresetn),
        // Port A — compute tile side (L2↔L1 transfers driven by tpu.sv FSM)
        .ct_addr_a(l2_ct_addr),
        .ct_din_a(l2_ct_din),
        .ct_dout_a(l2_ct_dout),
        .ct_en_a(l2_ct_en),
        .ct_we_a(l2_ct_we),
        // Port B — device memory side (tma_engine handles copies)
        .dm_addr(dm_l2_addr),
        .dm_din(dm_l2_din),
        .dm_dout(dm_l2_dout),
        .dm_en(dm_l2_en),
        .dm_we(dm_l2_we),
        // Host-controlled transfer (modes 5/6)
        .start_dm_to_l2(start_dm_to_l2),
        .start_l2_to_dm(start_l2_to_dm),
        .xfer_dm_base(addr_devmem),
        .xfer_l2_base(addr_l2),
        .xfer_len(dma_len[15:0]),
        .xfer_done(xfer_l2_done),
        // TMA instruction port (from compute_tile tensorcore)
        .tma_req(ct_tma_req),
        .tma_dir(ct_tma_dir),
        .tma_dm_base(ct_tma_dm_base),
        .tma_l2_base(ct_tma_l2_base),
        .tma_len(ct_tma_len),
        .tma_done(l2_tma_done)
    );

    // --- Compute Tile ---
    compute_tile #(
        .ADDR_WIDTH(13),
        .DATA_WIDTH(32)
    ) u_compute_tile (
        .clk(s00_axi_aclk),
        .rst_n(s00_axi_aresetn),
        // Control
        .start(start_compute_tile),
        .done(compute_tile_done),
        // DMA Instruction (IRAM loads, mode 4)
        .instr_write_en(instr_write_en && write_pointer[0]),
        .iram_addr(iram_addr),
        .dma_iram_din(dma_iram_din),
        // DMA Data — L1 Port A, used for L2↔L1 block transfers (modes 7/8)
        .base_addr(addr_ram),
        .dma_wr_en(l1_dma_wr_en),
        .dma_wr_data(l1_dma_wr_data),
        .dma_write_pointer(l1_dma_write_ptr),
        .dma_rd_en(l1_dma_rd_en),
        .dma_rd_data(l1_dma_rd_data),
        .dma_read_pointer(l1_dma_read_ptr),
        // TMA signals (tensorcore → l2_tile)
        .tma_req(ct_tma_req),
        .tma_dir(ct_tma_dir),
        .tma_dm_base(ct_tma_dm_base),
        .tma_l2_base(ct_tma_l2_base),
        .tma_len(ct_tma_len),
        .tma_done(l2_tma_done)
    );

	endmodule
