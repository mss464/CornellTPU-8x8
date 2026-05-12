`timescale 1ns / 1ps
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
    // Instruction RAM (Port A: DMA, Port B: PC Fetch)
    // =========================================================================
    logic [7:0]  pc_val;
    logic [63:0] current_instr;

    blk_mem_gen_1 I_bram (
        .clka  (clk),
        .ena   (1'b1),
        .wea   (instr_write_en),
        .addra (iram_addr),
        .dina  (dma_iram_din),
        .douta (),

        .clkb  (clk),
        .enb   (1'b1),
        .web   (1'b0),
        .addrb (pc_val),
        .dinb  (64'b0),
        .doutb (current_instr)
    );

    // =========================================================================
    // PC & Control FSM
    // =========================================================================
    logic pc_enable, pc_load;
    logic [7:0] pc_load_val;

    pc #(
        .PC_WIDTH(8)
    ) u_pc (
        .clk         (clk),
        .rst_n       (rst_n),
        .PC_enable   (pc_enable),
        .PC_load     (pc_load),
        .PC_load_val (pc_load_val),
        .PC          (pc_val)
    );

    // =========================================================================
    // Decoder
    // =========================================================================
    logic [22:0] len;
    logic [9:0]  opcode;
    logic [12:0] addr_a, addr_b, addr_out, addr_const;
    logic [1:0]  mode;
    logic [2:0]  vpu_type, vreg_dst, vreg_a, vreg_b, vpu_opcode;
    logic        scalar_b;

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
    // Scratchpad (L1 Data Memory)
    // =========================================================================
    logic [ADDR_WIDTH-1:0]           comp_addr_b;
    logic [NUM_BANKS*DATA_WIDTH-1:0] comp_din_b;
    logic [NUM_BANKS*DATA_WIDTH-1:0] comp_dout_b;
    logic                            comp_en_b;
    logic [NUM_BANKS-1:0]            comp_we_b;

    // Map oc_addr_a to scratchpad DMA port
    wire [15:0] sp_write_ptr = {3'b0, oc_addr_a};
    wire [15:0] sp_read_ptr  = {3'b0, oc_addr_a};

    scratchpad #(
        .ADDR_WIDTH(ADDR_WIDTH),
        .DATA_WIDTH(DATA_WIDTH),
        .NUM_BANKS (NUM_BANKS)
    ) u_scratchpad (
        .clk               (clk),
        .rst_n             (rst_n),
        .base_addr         ({ADDR_WIDTH{1'b0}}),
        .dma_wr_en         (oc_en_a && oc_we_a),
        .dma_wr_data       (oc_din_a),
        .dma_write_pointer (sp_write_ptr),
        .dma_rd_en         (oc_en_a && !oc_we_a),
        .dma_rd_data       (oc_dout_a),
        .dma_read_pointer  (sp_read_ptr),
        .dma_comp_addr_b   (comp_addr_b),
        .dma_comp_din_b    (comp_din_b),
        .dma_comp_dout_b   (comp_dout_b),
        .dma_comp_en_b     (comp_en_b),
        .dma_comp_we_b     (comp_we_b)
    );

    // =========================================================================
    // Compute Core (MXU + VPU SIMD + Vector Add)
    // =========================================================================
    logic start_systolic, start_vadd, start_vpu;
    logic systolic_done, vadd_done, vpu_done;

    compute_core #(
        .ADDR_WIDTH(ADDR_WIDTH),
        .DATA_WIDTH(DATA_WIDTH),
        .NUM_BANKS (NUM_BANKS)
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
        .vpu_type_compute       (vpu_type),
        .vreg_dst_compute       (vreg_dst),
        .vreg_a_compute         (vreg_a),
        .vreg_b_compute         (vreg_b),
        .vpu_opcode_compute     (vpu_opcode),
        .scalar_b_compute       (scalar_b),
        .bram_addr_b            (comp_addr_b),
        .bram_din_b             (comp_din_b),
        .bram_dout_b            (comp_dout_b),
        .bram_en_b              (comp_en_b),
        .bram_we_b              (comp_we_b)
    );

    // =========================================================================
    // Orchestration FSM
    // =========================================================================
    typedef enum logic [2:0] {
        IDLE      = 3'd0,
        FETCH     = 3'd1,
        DECODE    = 3'd2,
        EXECUTE   = 3'd3,
        HALT      = 3'd4,
        FETCH_WAIT = 3'd5
    } state_t;

    state_t state;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state           <= IDLE;
            pc_enable       <= 0;
            pc_load         <= 0;
            pc_load_val     <= 0;
            start_systolic  <= 0;
            start_vadd      <= 0;
            start_vpu       <= 0;
            done            <= 0;
        end else begin
            // Default pulse signals
            pc_enable       <= 0;
            pc_load         <= 0;
            start_systolic  <= 0;
            start_vadd      <= 0;
            start_vpu       <= 0;
            done            <= 0;

            case (state)
                IDLE: begin
                    if (start) begin
                        pc_load     <= 1'b1;
                        pc_load_val <= 8'd0;
                        state       <= FETCH;
                    end
                end

                FETCH: begin
                    state <= FETCH_WAIT;
                end

                FETCH_WAIT: begin
                    state <= DECODE;
                end

                DECODE: begin
                    if (opcode == 10'h3FF) begin // HALT
                        state <= HALT;
                    end else begin
                        // Dispatch based on mode
                        case (mode)
                            2'b00: start_vpu      <= 1'b1;
                            2'b01: start_systolic <= 1'b1;
                            2'b10: start_vadd     <= 1'b1;
                            default: ;
                        endcase
                        state <= EXECUTE;
                    end
                end

                EXECUTE: begin
                    if (systolic_done || vpu_done || vadd_done) begin
                        pc_enable <= 1'b1;
                        state     <= FETCH;
                    end
                end

                HALT: begin
                    done  <= 1'b1;
                    state <= IDLE;
                end
            endcase
        end
    end

endmodule
