`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Module Name: vpu_simd
// Description: SIMD Vector Processing Unit with register file
//              - 8-lane SIMD execution (8 parallel vpu_op ALU instances)
//              - Vector register file (V0-V7)
//              - Supports VLOAD (wide), VSTORE (wide), VCOMPUTE operations
//              - Scalar broadcast support for vector-scalar operations
//
// KEY DIFFERENCE from original: bram_we is [NUM_LANES-1:0] (per-lane)
// to match compute_core.sv which declares: logic [NUM_BANKS-1:0] vpu_we_b
//
// VLOAD/VSTORE use a single wide BRAM transaction (all 8 lanes at once)
// rather than 8 sequential scalar reads/writes.
//////////////////////////////////////////////////////////////////////////////////

module vpu_simd #(
    parameter int DATA_W    = 32,
    parameter int ADDR_W    = 13,
    parameter int NUM_LANES = 8
)(
    input  logic                         clk,
    input  logic                         rst_n,

    // Instruction fields
    input  logic [ADDR_W-1:0]           addr_a,
    input  logic [ADDR_W-1:0]           addr_b,
    input  logic [ADDR_W-1:0]           addr_out,
    input  logic [9:0]                  opcode,
    input  logic [ADDR_W-1:0]          addr_const,
    input  logic [2:0]                  vpu_type,
    input  logic [2:0]                  vreg_dst,
    input  logic [2:0]                  vreg_a,
    input  logic [2:0]                  vreg_b,
    input  logic [2:0]                  vpu_opcode,
    input  logic                        scalar_b,
    input  logic                        start,

    // Wide BRAM interface (NUM_LANES banks, each DATA_W wide)
    output logic [ADDR_W-1:0]           bram_addr,
    output logic [NUM_LANES*DATA_W-1:0] bram_din,
    input  logic [NUM_LANES*DATA_W-1:0] bram_dout,
    output logic                        bram_en,
    output logic [NUM_LANES-1:0]        bram_we,

    output logic                        done
);

    // vpu_type encoding
    localparam VPU_SCALAR   = 3'b000;
    localparam VPU_VLOAD    = 3'b001;
    localparam VPU_VSTORE   = 3'b010;
    localparam VPU_VCOMPUTE = 3'b011;

    //---------------------------------------------------------------------
    // Scalar VPU sub-unit (legacy, vpu_type == 0)
    //---------------------------------------------------------------------
    logic            start_scalar, done_scalar;
    logic [ADDR_W-1:0] bram_addr_sc;
    logic [DATA_W-1:0] bram_din_sc;
    logic              bram_en_sc, bram_we_sc;

    assign start_scalar = start && (vpu_type == VPU_SCALAR);

    vpu #(
        .DATA_W   (DATA_W),
        .ADDR_W   (ADDR_W),
        .OP_W     (10),
        .INST_ADDR(5),
        .M        (4)
    ) u_scalar (
        .clk            (clk),
        .rst_n          (rst_n),
        .start          (start_scalar),
        .inst_addr_a    (addr_a),
        .inst_addr_b    (addr_b),
        .inst_addr_c    (addr_out),
        .inst_addr_const(addr_const),
        .opcode         (opcode),
        .bram_addr      (bram_addr_sc),
        .bram_din       (bram_din_sc),
        .bram_dout      (bram_dout[DATA_W-1:0]),
        .bram_en        (bram_en_sc),
        .bram_we        (bram_we_sc),
        .done           (done_scalar)
    );

    //---------------------------------------------------------------------
    // SIMD datapath signals
    //---------------------------------------------------------------------
    logic                         start_simd;
    logic                         done_simd;
    logic [ADDR_W-1:0]            bram_addr_simd;
    logic [NUM_LANES*DATA_W-1:0]  bram_din_simd;
    logic                         bram_en_simd;
    logic [NUM_LANES-1:0]         bram_we_simd;
    logic                         active_scalar;

    assign start_simd = start && (vpu_type != VPU_SCALAR);

    //---------------------------------------------------------------------
    // Output mux
    //---------------------------------------------------------------------
    always_comb begin
        if (active_scalar) begin
            bram_addr = bram_addr_sc;
            bram_din  = {NUM_LANES{bram_din_sc}};
            bram_en   = bram_en_sc;
            bram_we   = bram_we_sc ? {{(NUM_LANES-1){1'b0}}, 1'b1} : '0;
            done      = done_scalar;
        end else begin
            bram_addr = bram_addr_simd;
            bram_din  = bram_din_simd;
            bram_en   = bram_en_simd;
            bram_we   = bram_we_simd;
            done      = done_simd;
        end
    end

    //---------------------------------------------------------------------
    // Vector Register File
    //---------------------------------------------------------------------
    logic [2:0]                        rf_rd_addr_a, rf_rd_addr_b, rf_wr_addr;
    logic [NUM_LANES-1:0][DATA_W-1:0]  rf_rd_data_a, rf_rd_data_b;
    logic [NUM_LANES-1:0][DATA_W-1:0]  rf_wr_data;
    logic                              rf_wr_en;

    vec_regfile #(
        .NUM_REGS  (8),
        .ELEM_WIDTH(DATA_W),
        .NUM_ELEMS (NUM_LANES)
    ) u_regfile (
        .clk      (clk),
        .rst_n    (rst_n),
        .rd_addr_a(rf_rd_addr_a),
        .rd_data_a(rf_rd_data_a),
        .rd_addr_b(rf_rd_addr_b),
        .rd_data_b(rf_rd_data_b),
        .wr_en    (rf_wr_en),
        .wr_addr  (rf_wr_addr),
        .wr_data  (rf_wr_data)
    );

    //---------------------------------------------------------------------
    // 8 Parallel ALU lanes
    //---------------------------------------------------------------------
    logic [NUM_LANES-1:0][DATA_W-1:0] alu_result;

    generate
        for (genvar i = 0; i < NUM_LANES; i++) begin : g_alu
            logic [DATA_W-1:0] op_b;
            assign op_b = scalar_b ? rf_rd_data_b[0] : rf_rd_data_b[i];

            vpu_op #(.DATA_W(DATA_W), .OP_W(3)) u_alu (
                .start      (1'b1),
                .operand0   (rf_rd_data_a[i]),
                .operand1   (op_b),
                .opcode     (vpu_opcode),
                .result_out (alu_result[i])
            );
        end
    endgenerate

    //---------------------------------------------------------------------
    // SIMD FSM
    //---------------------------------------------------------------------
    typedef enum logic [3:0] {
        IDLE,
        VLOAD_REQ,
        VLOAD_W1,
        VLOAD_W2,
        VLOAD_W3,
        VLOAD_CAPTURE,
        VLOAD_WB,
        VSTORE_WAIT,
        VSTORE_REQ,
        VCOMPUTE_READ,
        VCOMPUTE_EXEC,
        DONE_ST
    } state_t;

    state_t state;

    logic [ADDR_W-1:0]              saved_addr_a, saved_addr_out;
    logic [2:0]                     saved_vreg_dst, saved_vreg_a, saved_vreg_b;
    logic [NUM_LANES-1:0][DATA_W-1:0] load_buf;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state          <= IDLE;
            bram_en_simd   <= 1'b0;
            bram_we_simd   <= '0;
            bram_addr_simd <= '0;
            bram_din_simd  <= '0;
            rf_wr_en       <= 1'b0;
            rf_wr_addr     <= '0;
            rf_wr_data     <= '0;
            rf_rd_addr_a   <= '0;
            rf_rd_addr_b   <= '0;
            done_simd      <= 1'b0;
            active_scalar  <= 1'b1;
            load_buf       <= '0;
            saved_addr_a   <= '0;
            saved_addr_out <= '0;
            saved_vreg_dst <= '0;
            saved_vreg_a   <= '0;
            saved_vreg_b   <= '0;
        end else begin
            // Pulse defaults
            done_simd    <= 1'b0;
            bram_we_simd <= '0;
            bram_en_simd <= 1'b0;
            rf_wr_en     <= 1'b0;

            case (state)
                //----------------------------------------------------------
                IDLE: begin
                    if (start) begin
                        active_scalar <= (vpu_type == VPU_SCALAR);
                    end

                    if (start_simd) begin
                        saved_addr_a   <= addr_a;
                        saved_addr_out <= addr_out;
                        saved_vreg_dst <= vreg_dst;
                        saved_vreg_a   <= vreg_a;
                        saved_vreg_b   <= vreg_b;
                        case (vpu_type)
                            VPU_VLOAD: begin
                                state <= VLOAD_REQ;
                            end
                            VPU_VSTORE: begin
                                rf_rd_addr_a <= vreg_a;
                                state <= VSTORE_WAIT;  // wait 1 cycle for RF read
                            end
                            VPU_VCOMPUTE: begin
                                rf_rd_addr_a <= vreg_a;
                                rf_rd_addr_b <= vreg_b;
                                state <= VCOMPUTE_READ;
                            end
                            default: state <= DONE_ST;
                        endcase
                    end
                end

                //----------------------------------------------------------
                // VLOAD: single wide read (all 8 lanes in one transaction)
                //----------------------------------------------------------
                VLOAD_REQ: begin
                    bram_en_simd   <= 1'b1;
                    bram_addr_simd <= saved_addr_a;
                    state          <= VLOAD_W1;
                end

                VLOAD_W1: begin bram_en_simd <= 1'b1; state <= VLOAD_W2; end
                VLOAD_W2: begin bram_en_simd <= 1'b1; state <= VLOAD_W3; end
                VLOAD_W3: begin                        state <= VLOAD_CAPTURE; end

                VLOAD_CAPTURE: begin
                    // Unpack wide BRAM dout into load buffer
                    for (int i = 0; i < NUM_LANES; i++) begin
                        load_buf[i] <= bram_dout[i*DATA_W +: DATA_W];
                    end
                    state <= VLOAD_WB;
                end

                VLOAD_WB: begin
                    // load_buf is now stable — write to register file
                    rf_wr_en   <= 1'b1;
                    rf_wr_addr <= saved_vreg_dst;
                    rf_wr_data <= load_buf;
                    state      <= DONE_ST;
                end

                //----------------------------------------------------------
                // VSTORE: single wide write (all 8 lanes in one transaction)
                //----------------------------------------------------------
                VSTORE_WAIT: begin
                    // RF read latency: rf_rd_data_a valid this cycle
                    state <= VSTORE_REQ;
                end

                VSTORE_REQ: begin
                    bram_en_simd   <= 1'b1;
                    bram_we_simd   <= {NUM_LANES{1'b1}};
                    bram_addr_simd <= saved_addr_out;
                    for (int i = 0; i < NUM_LANES; i++) begin
                        bram_din_simd[i*DATA_W +: DATA_W] <= rf_rd_data_a[i];
                    end
                    state <= DONE_ST;
                end

                //----------------------------------------------------------
                // VCOMPUTE: parallel ALU
                //----------------------------------------------------------
                VCOMPUTE_READ: begin
                    // RF read latency
                    state <= VCOMPUTE_EXEC;
                end

                VCOMPUTE_EXEC: begin
                    rf_wr_en   <= 1'b1;
                    rf_wr_addr <= saved_vreg_dst;
                    rf_wr_data <= alu_result;
                    state      <= DONE_ST;
                end

                //----------------------------------------------------------
                DONE_ST: begin
                    done_simd <= 1'b1;
                    state     <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end

endmodule
