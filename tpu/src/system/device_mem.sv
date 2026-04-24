`timescale 1ns / 1ps

module device_mem #(
    parameter ADDR_WIDTH = 19,
    parameter DATA_WIDTH = 256,
    parameter AXI_ADDR_WIDTH = 32
)(
    input  logic                     clk,
    input  logic                     rst_n,
    input  logic [31:0]              ddr_phys_base,

    // Control interface
    input  logic [ADDR_WIDTH-1:0]    base_addr,

    // Write interface — Port A (from Slave Stream)
    input  logic                     dma_wr_en,
    input  logic [DATA_WIDTH-1:0]    dma_wr_data,
    input  logic [18:0]              dma_write_pointer,
    output logic                     dma_wr_ready,

    // Read interface — Port A (to Master Stream)
    input  logic                     dma_rd_cmd_en,
    output logic [DATA_WIDTH-1:0]    dma_rd_data,
    input  logic [18:0]              dma_read_pointer,
    output logic                     dma_rd_cmd_ready,
    output logic                     dma_rd_valid,

    // L2 tile port — Port B (from/to tma_engine)
    input  logic [ADDR_WIDTH-1:0]    l2_addr_b,
    input  logic [31:0]              l2_din_b,
    output logic [31:0]              l2_dout_b,
    input  logic                     l2_en_b,
    input  logic                     l2_we_b,
    output logic                     l2_ready_b,
    output logic                     l2_rvalid_b,
    output logic                     l2_bvalid_b,

    // AXI4 Master Interface
    output logic [AXI_ADDR_WIDTH-1:0] m_axi_awaddr,
    output logic [7:0]                m_axi_awlen,
    output logic [2:0]                m_axi_awsize,
    output logic [1:0]                m_axi_awburst,
    output logic                      m_axi_awvalid,
    input  logic                      m_axi_awready,

    output logic [127:0]              m_axi_wdata,
    output logic [15:0]               m_axi_wstrb,
    output logic                      m_axi_wlast,
    output logic                      m_axi_wvalid,
    input  logic                      m_axi_wready,

    input  logic [1:0]                m_axi_bresp,
    input  logic                      m_axi_bvalid,
    output logic                      m_axi_bready,

    output logic [AXI_ADDR_WIDTH-1:0] m_axi_araddr,
    output logic [7:0]                m_axi_arlen,
    output logic [2:0]                m_axi_arsize,
    output logic [1:0]                m_axi_arburst,
    output logic [2:0]                m_axi_arprot,
    output logic [3:0]                m_axi_arcache,
    output logic                      m_axi_arvalid,
    input  logic                      m_axi_arready,

    input  logic [127:0]              m_axi_rdata,
    input  logic [1:0]                m_axi_rresp,
    input  logic                      m_axi_rlast,
    input  logic                      m_axi_rvalid,
    output logic                      m_axi_rready,

    // Write Attributes
    output logic [2:0]                m_axi_awprot,
    output logic [3:0]                m_axi_awcache,
    
    output logic                      axi_timeout_err
);

    // =========================================================================
    // AXI Constants (Standardized for 128-bit bursts of 2)
    // =========================================================================
    assign m_axi_awsize  = 3'b100; // 16 bytes (128-bit) -> 2^4 = 16
    assign m_axi_awburst = 2'b01;  // INCR
    assign m_axi_arsize  = 3'b100; 
    assign m_axi_arburst = 2'b01;  
    assign m_axi_awprot  = 3'b000;
    assign m_axi_awcache = 4'b0011; // Normal, Non-cacheable, Modifiable, Bufferable
    assign m_axi_arprot  = 3'b000;
    assign m_axi_arcache = 4'b0011;
    
    // Address translations — all offsets relative to ddr_phys_base
    wire [AXI_ADDR_WIDTH-1:0] base_byte_addr  = {13'b0, base_addr[15:0]} << 5;
    
    // Port B addresses are word-aligned for 32-bit (shifted by 2 = 4 bytes)
    wire [AXI_ADDR_WIDTH-1:0] l2_axi_addr     = ddr_phys_base + base_byte_addr + ({13'b0, l2_addr_b} << 2);
    wire [AXI_ADDR_WIDTH-1:0] l2_axi_addr_aligned = {l2_axi_addr[AXI_ADDR_WIDTH-1:5], 5'b00000};
    wire [2:0] l2_word_offset = l2_addr_b[2:0];

    // Read and Write FSM States
    typedef enum logic [1:0] {WR_IDLE, WR_ISSUE, WR_RESP} wr_state_t;
    wr_state_t dm_wr_state;

    typedef enum logic [1:0] {RD_IDLE, RD_ADDR, RD_DATA} rd_state_t;
    rd_state_t dm_rd_state;

    // Registers for AXI Outputs
    logic [AXI_ADDR_WIDTH-1:0] dma_axi_wr_addr;
    logic                      m_axi_awvalid_reg;
    logic                      m_axi_wvalid_reg;
    logic [127:0]              m_axi_wdata_reg;
    logic [255:0]              wdata_buffer;
    logic                      w_beat_count;
    logic [11:0]               wr_timeout_cnt;
    logic                      wr_timeout_latched;
    
    logic [AXI_ADDR_WIDTH-1:0] dma_axi_rd_addr;
    logic                      m_axi_arvalid_reg;
    logic [255:0]              rdata_buffer;
    logic                      r_beat_count;

    // Output Registers for DMA logic
    logic dma_rd_valid_reg;
    logic [DATA_WIDTH-1:0] dma_rd_data_reg;

    assign dma_wr_ready = (dm_wr_state == WR_IDLE);
    assign dma_rd_cmd_ready = (dm_rd_state == RD_IDLE);
    assign dma_rd_valid = dma_rd_valid_reg;
    assign dma_rd_data = dma_rd_data_reg;
    assign axi_timeout_err = wr_timeout_latched;

    wire port_b_active = l2_en_b;
    wire l2_aw_valid = l2_en_b && l2_we_b;
    wire l2_ar_valid = l2_en_b && !l2_we_b;

    logic [255:0] l2_wdata_expanded;
    logic [31:0]  l2_wstrb_expanded;
    
    always_comb begin
        l2_wdata_expanded = '0;
        l2_wstrb_expanded = '0;
        l2_wdata_expanded[l2_word_offset * 32 +: 32] = l2_din_b;
        l2_wstrb_expanded[l2_word_offset * 4  +: 4]  = 4'hF;
    end
    
    assign l2_ready_b  = l2_we_b ? (m_axi_awready && m_axi_wready) : m_axi_arready;
    assign l2_bvalid_b = m_axi_bvalid;

    reg [2:0] pending_l2_offset;
    always_ff @(posedge clk) begin
        if (l2_ar_valid && m_axi_arready) begin
            pending_l2_offset <= l2_word_offset;
        end
    end
    
    assign l2_dout_b = m_axi_rdata[pending_l2_offset * 32 +: 32];
    assign l2_rvalid_b = m_axi_rvalid && port_b_active;

    // =========================================================================
    // Write FSM (DMA Port A)
    // =========================================================================
    logic aw_done;
    logic w_done;
    logic b_done;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            dm_wr_state       <= WR_IDLE;
            m_axi_awvalid_reg  <= 0;
            m_axi_wvalid_reg   <= 0;
            m_axi_wdata_reg    <= 0;
            dma_axi_wr_addr    <= 0;
            wdata_buffer       <= 0;
            w_beat_count       <= 0;
            aw_done            <= 0;
            w_done             <= 0;
            b_done             <= 0;
            wr_timeout_cnt     <= 0;
            wr_timeout_latched <= 0;
        end else begin
            case (dm_wr_state)
                WR_IDLE: begin
                    if (dma_wr_en) begin
                        m_axi_awvalid_reg <= 1;
                        dma_axi_wr_addr <= ddr_phys_base + base_byte_addr + ({13'b0, dma_write_pointer} << 5);
                        m_axi_wvalid_reg <= 1;
                        m_axi_wdata_reg <= dma_wr_data[127:0];
                        wdata_buffer <= dma_wr_data;
                        w_beat_count <= 0;
                        aw_done <= 0;
                        w_done <= 0;
                        b_done <= 0;
                        wr_timeout_cnt <= 0;
                        dm_wr_state <= WR_ISSUE;
                    end
                end

                WR_ISSUE: begin
                    if (wr_timeout_cnt == 12'hFFF) begin
                        wr_timeout_latched <= 1;
                        dm_wr_state <= WR_IDLE;
                    end else begin
                        wr_timeout_cnt <= wr_timeout_cnt + 1;
                    end

                    if (!aw_done && m_axi_awvalid_reg && m_axi_awready) begin
                        m_axi_awvalid_reg <= 0;
                        aw_done <= 1;
                    end

                    if (!w_done && m_axi_wvalid_reg && m_axi_wready) begin
                        if (w_beat_count == 0) begin
                            w_beat_count <= 1;
                            m_axi_wdata_reg <= wdata_buffer[255:128];
                        end else begin
                            m_axi_wvalid_reg <= 0;
                            w_done <= 1;
                        end
                    end

                    if (!b_done && m_axi_bvalid) begin
                        b_done <= 1;
                    end

                    if (aw_done && w_done && (b_done || m_axi_bvalid)) begin
                        dm_wr_state <= WR_IDLE;
                    end
                end
                default: dm_wr_state <= WR_IDLE;
            endcase
        end
    end

    // =========================================================================
    // Read FSM (DMA Port A)
    // =========================================================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            dm_rd_state <= RD_IDLE;
            m_axi_arvalid_reg <= 0;
            dma_axi_rd_addr <= 0;
            dma_rd_valid_reg <= 0;
            dma_rd_data_reg <= 0;
            rdata_buffer <= 0;
            r_beat_count <= 0;
        end else begin
            case (dm_rd_state)
                RD_IDLE: begin
                    dma_rd_valid_reg <= 0;
                    // FIX BUG: ensure dma_rd_cmd_ready_reg evaluates to 1 properly to avoid duplicate commands
                    if (dma_rd_cmd_en) begin
                        m_axi_arvalid_reg <= 1;
                        dma_axi_rd_addr <= ddr_phys_base + base_byte_addr + ({13'b0, dma_read_pointer} << 5);
                        r_beat_count <= 0;
                        dm_rd_state <= RD_ADDR;
                    end
                end

                RD_ADDR: begin
                    if (m_axi_arvalid_reg && m_axi_arready) begin
                        m_axi_arvalid_reg <= 0;
                        dm_rd_state <= RD_DATA;
                    end
                end

                RD_DATA: begin
                    if (m_axi_rvalid) begin
                        if (r_beat_count == 0) begin
                            rdata_buffer[127:0] <= m_axi_rdata;
                            r_beat_count <= 1;
                        end else begin
                            dma_rd_data_reg <= {m_axi_rdata, rdata_buffer[127:0]};
                            dma_rd_valid_reg <= 1;
                            dm_rd_state <= RD_IDLE;
                        end
                    end
                end
            endcase
        end
    end

    // =========================================================================
    // AXI Bus Muxing (Standardized for 128-bit Native Fabric)
    // =========================================================================
    assign m_axi_awlen   = port_b_active ? 8'd0 : 8'd1; 
    assign m_axi_arlen   = port_b_active ? 8'd0 : 8'd1; 
    
    assign m_axi_awvalid = port_b_active ? l2_aw_valid : m_axi_awvalid_reg;
    assign m_axi_awaddr  = port_b_active ? l2_axi_addr_aligned : dma_axi_wr_addr;
    
    assign m_axi_wvalid  = port_b_active ? l2_aw_valid : m_axi_wvalid_reg;
    assign m_axi_wdata   = port_b_active ? l2_wdata_expanded[127:0] : m_axi_wdata_reg;
    assign m_axi_wstrb   = port_b_active ? l2_wstrb_expanded[15:0] : 16'hFFFF;
    assign m_axi_wlast   = port_b_active ? 1'b1 : (w_beat_count == 1'b1);
    
    assign m_axi_arvalid = port_b_active ? l2_ar_valid : m_axi_arvalid_reg;
    assign m_axi_araddr  = port_b_active ? l2_axi_addr_aligned : dma_axi_rd_addr;
    
    assign m_axi_rready  = 1'b1;
    assign m_axi_bready  = 1'b1;  // Always accept write responses (AXI-legal, avoids SmartConnect stalls)

endmodule
