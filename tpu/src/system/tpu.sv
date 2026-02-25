`timescale 1 ns / 1 ps

	module tpu #
	(
		// Users to add parameters here

		// User parameters ends
		// Do not modify the parameters beyond this line


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
		// Users to add ports here

		// User ports ends
		// Do not modify the ports beyond this line


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
	
	// 32-bit buses from AXI slave
    wire [31:0] slv_reg0_bus;
    wire [31:0] slv_reg3_bus;
    wire [31:0] slv_reg4_bus;
    wire [31:0] slv_reg5_bus;
    wire [31:0] slv_reg6_bus;


//    wire [1:0]  instr = slv_reg0_bus[1:0];   // instruction selector
    reg         instr_ready;        // set while idle
    reg         stream_ready;       // BRAM DMA handshake ready
    wire [12:0] addr_ram    = slv_reg3_bus[12:0];
    wire [15:0] addr_devmem = slv_reg4_bus[15:0];
    wire [31:0] dma_len       = slv_reg6_bus;
    
    wire [2:0] tpu_mode = slv_reg0_bus[2:0];
    
    // Unified status signals
    reg start_compute_tile;
    wire compute_tile_done;
    
    // DMA Data Interface
    reg data_write_en, instr_write_en, read_en, start_stream;
    wire write_bram_done, read_bram_done;
    wire [15:0] write_pointer;
    wire [15:0] read_pointer;
    
    wire [31:0] dma_dram_din;
    wire [63:0] dma_iram_din;
    wire [31:0] dma_dout;

// Instantiation of Axi Bus Interface S00_AXI
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
		
		// === NEW USER STATUS SIGNALS ===
        .instr_ready_ext(instr_ready),
        .stream_ready_ext(stream_ready),
        .slv_reg0_out(slv_reg0_bus),
        .slv_reg3_out(slv_reg3_bus),
        .slv_reg4_out(slv_reg4_bus),
        .slv_reg5_out(slv_reg5_bus),
        .slv_reg6_out(slv_reg6_bus)
	);

// Instantiation of Axi Bus Interface S00_AXIS
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
		.tpu_mode_stream(tpu_mode)
	);

// Instantiation of Axi Bus Interface M00_AXIS
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
		
		.data_to_ddr(dma_dout),
		.len(dma_len),
		.read_en(start_stream),
		.done(read_bram_done),
		.read_pointer_stream(read_pointer)
	);

	
    // for loading to IRAM
    reg [7:0] iram_addr;
    
    always @(posedge s00_axi_aclk or negedge s00_axi_aresetn) begin
        if (!s00_axi_aresetn) begin
            iram_addr <= 0;
        end else if (instr_write_en && write_pointer[0]) begin
            iram_addr <= addr_ram[7:0] + write_pointer[7:1];
        end
    end

    //  FSM State encoding
    localparam IDLE         = 4'd0;
    localparam EXEC_WRITE   = 4'd1;
    localparam EXEC_READ    = 4'd2;
    localparam EXEC_COMPUTE = 4'd3;
    localparam WAIT_DONE    = 4'd8;
    
    reg [3:0] state = IDLE;
    
    //  Sequential FSM logic
    always @(posedge s00_axi_aclk or negedge s00_axi_aresetn) begin
        if (!s00_axi_aresetn) begin
            state         <= IDLE;
            instr_ready   <= 1'b1;
            stream_ready  <= 1'b1;
            data_write_en   <= 1'b0;
            instr_write_en <= 1'b0;
            read_en    <= 1'b0;
            start_compute_tile <= 1'b0;
            start_stream <= 1'b0;
        end else begin
            // defaults
            data_write_en   <= 1'b0;
            instr_write_en <= 1'b0;
            read_en    <= 1'b0;
            start_compute_tile <= 1'b0;
            start_stream <= 1'b0;

            case (state)
                //------------------------------------------------------
                IDLE: begin
                    instr_ready <= 1'b1; // ready for next instruction
                    if (tpu_mode == 3'd1) begin // WRITE_BRAM_DATA
                        instr_ready  <= 1'b0;
                        data_write_en  <= 1'b1;
                        stream_ready <= 1'b1; // BRAM ready for DMA stream
                        state        <= EXEC_WRITE;
                    end else if (tpu_mode == 3'd2) begin // READ_BRAM
                        instr_ready  <= 1'b0;
                        read_en   <= 1'b1;
                        start_stream <= 1'b1;
                        stream_ready <= 1'b1;
                        state        <= EXEC_READ;
                    end else if (tpu_mode == 3'd3) begin // COMPUTE
                        instr_ready  <= 1'b0;
                        start_compute_tile <= 1'b1;
                        stream_ready <= 1'b0;
                        state        <= EXEC_COMPUTE;
                    end else if (tpu_mode == 3'd4) begin  // WRITE_IRAM_DATA
                        instr_ready  <= 1'b0;
                        instr_write_en  <= 1'b1;
                        stream_ready <= 1'b1; // BRAM ready for DMA stream
                        state        <= EXEC_WRITE;
                    end
                end
    
                //------------------------------------------------------
                EXEC_WRITE: begin
                    // Wait until BRAM transfer finishes
                    stream_ready <= 1'b1;
                    if (tpu_mode == 3'd1) begin
                        data_write_en <= 1'b1;
                    end else if (tpu_mode == 3'd4) begin
                        instr_write_en <= 1'b1;
                    end
                    if (write_bram_done) begin
                        state <= WAIT_DONE;
                        end
                end
    
                //------------------------------------------------------
                EXEC_READ: begin
                    stream_ready <= 1'b1;
                    read_en <= 1'b1;
                    if (read_bram_done) begin
                        state <= WAIT_DONE;
                        end
                end
    
                //------------------------------------------------------
                EXEC_COMPUTE: begin
                    if (compute_tile_done) begin
                        state <= WAIT_DONE;
                    end
                end
                //------------------------------------------------------
                WAIT_DONE: begin
                    instr_ready <= 1'b1;
                    if (tpu_mode == 3'd0) begin
                        state <= IDLE;
                    end
                end
            endcase
        end
    end
    
    //  Instantiate submodules

    // Device Memory — host DMA target for modes 1/2
    wire [31:0] devmem_rd_data;
    device_mem #(
        .ADDR_WIDTH(16),
        .DATA_WIDTH(32)
    ) u_device_mem (
        .clk(s00_axi_aclk),
        .rst_n(s00_axi_aresetn),

        // Host DMA — Port A
        .base_addr(addr_devmem),
        .dma_wr_en(data_write_en),
        .dma_wr_data(dma_dram_din),
        .dma_write_pointer(write_pointer),
        .dma_rd_en(read_en),
        .dma_rd_data(devmem_rd_data),
        .dma_read_pointer(read_pointer),

        // L2 tile — Port B (stubbed for P1.2)
        .l2_addr_b(16'b0),
        .l2_din_b(32'b0),
        .l2_dout_b(),
        .l2_en_b(1'b0),
        .l2_we_b(1'b0)
    );

    assign dma_dout = devmem_rd_data;

    // Compute tile — L1 DMA ports tied off (data path now goes through device_mem)
    compute_tile #(
        .ADDR_WIDTH(13),
        .DATA_WIDTH(32)
    ) u_compute_tile (
        .clk(s00_axi_aclk),
        .rst_n(s00_axi_aresetn),

        // Control
        .start(start_compute_tile),
        .done(compute_tile_done),

        // DMA Instruction (still active — IRAM loads bypass device_mem)
        .instr_write_en(instr_write_en && write_pointer[0]),
        .iram_addr(iram_addr),
        .dma_iram_din(dma_iram_din),

        // DMA Data — tied off (no direct host→L1 path)
        .base_addr(13'b0),
        .dma_wr_en(1'b0),
        .dma_wr_data(32'b0),
        .dma_write_pointer(16'b0),
        .dma_rd_en(1'b0),
        .dma_rd_data(),
        .dma_read_pointer(16'b0)
    );
    
	// User logic ends

	endmodule
