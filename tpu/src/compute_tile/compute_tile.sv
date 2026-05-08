`timescale 1ns / 1ps
// ============================================================================
// compute_tile.sv — Compute Tile: Scratchpad + TensorCore
//
// Wraps:
//   - scratchpad.sv (8-bank interleaved L1 with mem_wrapper BRAMs)
//   - compute_core.sv (MXU + VPU SIMD + Vector Add)
//   - decoder.sv (instruction decode)
//   - pc.sv (program counter)
//   - Instruction BRAM (blk_mem_gen_1)
//
// Port A of scratchpad: 32-bit scalar DMA interface (for mem_ctrl sys↔OC)
// Port B of scratchpad: 256-bit wide interface (for compute_core)
//
// Also provides start/done handshake for compute_ctrl dispatch.
// ============================================================================

module compute_tile #(
    parameter ADDR_WIDTH     = 13,
    parameter DATA_WIDTH     = 32,
    parameter NUM_BANKS      = 8
)(
    input  logic clk,
    input  logic rst_n,

    // ── Compute control ────────────────────────────────────────────────
    input  logic        start,          // 1-cycle pulse from compute_ctrl
    output logic        done,           // 1-cycle pulse when program halts

    // ── Scalar DMA interface (Port A of scratchpad) ────────────────────
    //    Driven by mem_ctrl for modes 5/6 (sys↔onchip copy)
    input  logic [ADDR_WIDTH-1:0]  oc_addr_a,
    input  logic [DATA_WIDTH-1:0]  oc_din_a,
    output logic [DATA_WIDTH-1:0]  oc_dout_a,
    input  logic                   oc_en_a,
    input  logic                   oc_we_a,

    // ── Instruction DMA interface ──────────────────────────────────────
    input  logic        instr_write_en,
    input  logic [7:0]  iram_addr,
    input  logic [63:0] dma_iram_din
);

    // =========================================================================
    // Internal wires
    // =========================================================================

    // PC signals
    logic [7:0]  pc_val;
    logic        pc_enable;
    logic        pc_load;
    logic [7:0]  pc_load_val;

    // Decoder signals
    logic [63:0] current_instr;
    logic [22:0] len;
    logic [9:0]  opcode;
    logic [12:0] addr_a, addr_b, addr_out, addr_const;
    logic [1:0]  mode;

    // VPU SIMD fields
    logic [2:0]  vpu_type, vreg_dst, vreg_a, vreg_b, vpu_opcode;
    logic        scalar_b;

    // Compute unit control
    logic start_systolic, start_vpu, start_vadd;
    logic systolic_done, vpu_done, vadd_done;

    // Scratchpad Port B (compute-side, wide 256-bit)
    logic [ADDR_WIDTH-1:0]           comp_addr_b;
    logic [NUM_BANKS*DATA_WIDTH-1:0] comp_din_b;
    logic [NUM_BANKS*DATA_WIDTH-1:0] comp_dout_b;
    logic                            comp_en_b;
    logic [NUM_BANKS-1:0]            comp_we_b;

    // Scratchpad DMA-side wires (remapped from scalar Port A)
    // We re-use the scratchpad's DMA write/read interface for the scalar path
    // by driving it from oc_addr_a / oc_din_a / oc_en_a / oc_we_a.

    // =========================================================================
    // FSM for Instruction Orchestration
    // =========================================================================
    typedef enum logic [3:0] {
        IDLE         = 4'd0,
        EXEC_COMPUTE = 4'd3,
        WAIT_COMPUTE = 4'd4,
        FETCH_1      = 4'd5,
        FETCH_2      = 4'd6,
        FETCH_3      = 4'd7,
        HALT_STATE   = 4'd8
    } ct_state_t;

    ct_state_t state;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state          <= IDLE;
            done           <= 1'b0;
            start_systolic <= 1'b0;
            start_vpu      <= 1'b0;
            start_vadd     <= 1'b0;
            pc_load        <= 1'b0;
            pc_load_val    <= 8'd0;
        end else begin
            // Default pulse signals
            start_systolic <= 1'b0;
            start_vpu      <= 1'b0;
            start_vadd     <= 1'b0;
            pc_load        <= 1'b0;
            done           <= 1'b0;

            case (state)
                IDLE: begin
                    if (start) begin
                        pc_load     <= 1'b1;
                        pc_load_val <= 8'd0;
                        state       <= FETCH_1;
                    end
                end

                EXEC_COMPUTE: begin
                    // mode 3 is HALT
                    if (mode == 2'd3) begin
                        state <= HALT_STATE;
                    end else begin
                        case (mode)
                            2'b00: begin // VPU
                                start_vpu <= 1'b1;
                                state     <= WAIT_COMPUTE;
                            end
                            2'b01: begin // Systolic
                                start_systolic <= 1'b1;
                                state          <= WAIT_COMPUTE;
                            end
                            2'b10: begin // Vector Add
                                start_vadd <= 1'b1;
                                state      <= WAIT_COMPUTE;
                            end
                            default: state <= HALT_STATE;
                        endcase
                    end
                end

                WAIT_COMPUTE: begin
                    if (systolic_done || vpu_done || vadd_done) begin
                        state <= FETCH_1;
                    end
                end

                FETCH_1: state <= FETCH_2;
                FETCH_2: state <= FETCH_3;
                FETCH_3: state <= EXEC_COMPUTE;

                HALT_STATE: begin
                    done  <= 1'b1;
                    state <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end

    // PC enable: increment after current instruction completes execution
    assign pc_enable = (state == WAIT_COMPUTE &&
                        (systolic_done || vpu_done || vadd_done));

    // =========================================================================
    // PC: Program Counter
    // =========================================================================
    pc #(
        .PC_WIDTH(8)
    ) u_pc (
        .clk        (clk),
        .rst_n      (rst_n),
        .PC_enable  (pc_enable),
        .PC_load    (pc_load),
        .PC_load_val(pc_load_val),
        .PC         (pc_val)
    );

    // =========================================================================
    // Instruction BRAM (blk_mem_gen_1: 64-bit × 256)
    // =========================================================================
    blk_mem_gen_1 I_bram (
        // Port A — DMA side (instruction loading)
        .clka  (clk),
        .ena   (1'b1),
        .wea   (instr_write_en),
        .addra (iram_addr),
        .dina  (dma_iram_din),
        .douta (),

        // Port B — Compute side (instruction fetch)
        .clkb  (clk),
        .enb   (1'b1),
        .web   (1'b0),
        .addrb (pc_val),
        .dinb  (64'b0),
        .doutb (current_instr)
    );

    // =========================================================================
    // Decoder: Instruction Decoder
    // =========================================================================
    decoder u_decoder (
        .instr_decode      (current_instr),
        .len_decode        (len),
        .opcode_decode     (opcode),
        .addr_const_decode (addr_const),
        .addr_out_decode   (addr_out),
        .addr_b_decode     (addr_b),
        .addr_a_decode     (addr_a),
        .mode_decode       (mode),
        .vpu_type_decode   (vpu_type),
        .vreg_dst_decode   (vreg_dst),
        .vreg_a_decode     (vreg_a),
        .vreg_b_decode     (vreg_b),
        .vpu_opcode_decode (vpu_opcode),
        .scalar_b_decode   (scalar_b)
    );

    // =========================================================================
    // Compute Core (MXU + VPU SIMD + Vector Add)
    // =========================================================================
    compute_core #(
        .ADDR_WIDTH (ADDR_WIDTH),
        .DATA_WIDTH (DATA_WIDTH),
        .NUM_BANKS  (NUM_BANKS),
        .VPU_DATA_W (DATA_WIDTH),
        .VPU_ADDR_W (ADDR_WIDTH),
        .VPU_OP_W   (4),
        .VPU_IADDR_W(5)
    ) u_compute_core (
        .clk                    (clk),
        .rst_n                  (rst_n),
        .mode_compute           (mode),
        .addr_a_compute         (addr_a),
        .addr_b_compute         (addr_b),
        .addr_out_compute       (addr_out),
        .addr_const_compute     (addr_const),
        .opcode_compute         (opcode),
        .len_compute            (len),
        .start_systolic_compute (start_systolic),
        .start_vadd_compute     (start_vadd),
        .start_vpu_compute      (start_vpu),
        .systolic_done_compute  (systolic_done),
        .vadd_done_compute      (vadd_done),
        .vpu_done_compute       (vpu_done),

        // VPU SIMD fields
        .vpu_type_compute       (vpu_type),
        .vreg_dst_compute       (vreg_dst),
        .vreg_a_compute         (vreg_a),
        .vreg_b_compute         (vreg_b),
        .vpu_opcode_compute     (vpu_opcode),
        .scalar_b_compute       (scalar_b),

        // BRAM Port B (wide) — connects to scratchpad Port B
        .bram_addr_b            (comp_addr_b),
        .bram_din_b             (comp_din_b),
        .bram_dout_b            (comp_dout_b),
        .bram_en_b              (comp_en_b),
        .bram_we_b              (comp_we_b)
    );

    // =========================================================================
    // Scratchpad (8-bank interleaved L1 memory)
    //
    // Port A: 32-bit scalar interface from mem_ctrl (sys↔OC copies)
    //   - We drive dma_wr_en/dma_rd_en from oc_en_a and oc_we_a
    //   - base_addr = 0 (flat addressing; address comes from oc_addr_a)
    //   - dma_write_pointer/dma_read_pointer = oc_addr_a
    //
    // Port B: 256-bit wide interface from compute_core
    // =========================================================================

    // Map scalar interface to scratchpad DMA ports
    wire sp_dma_wr_en = oc_en_a && oc_we_a;
    wire sp_dma_rd_en = oc_en_a && !oc_we_a;

    // Use the address directly as the pointer (base_addr = 0)
    wire [15:0] sp_write_ptr = {3'b0, oc_addr_a};
    wire [15:0] sp_read_ptr  = {3'b0, oc_addr_a};

    scratchpad #(
        .ADDR_WIDTH(ADDR_WIDTH),
        .DATA_WIDTH(DATA_WIDTH),
        .NUM_BANKS (NUM_BANKS)
    ) u_scratchpad (
        .clk               (clk),
        .rst_n             (rst_n),
        .base_addr         ({ADDR_WIDTH{1'b0}}),  // flat addressing

        // DMA write interface (scalar from mem_ctrl)
        .dma_wr_en         (sp_dma_wr_en),
        .dma_wr_data       (oc_din_a),
        .dma_write_pointer (sp_write_ptr),

        // DMA read interface (scalar to mem_ctrl)
        .dma_rd_en         (sp_dma_rd_en),
        .dma_rd_data       (oc_dout_a),
        .dma_read_pointer  (sp_read_ptr),

        // Compute-side BRAM port (Port B, wide)
        .dma_comp_addr_b   (comp_addr_b),
        .dma_comp_din_b    (comp_din_b),
        .dma_comp_dout_b   (comp_dout_b),
        .dma_comp_en_b     (comp_en_b),
        .dma_comp_we_b     (comp_we_b)
    );

endmodule
