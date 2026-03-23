`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Module Name: tensorcore
// Description: Centralized compute controller for systolic array and SIMD VPU.
//              Contains its own PC, Decoder, and Instruction BRAM.
//
// Instruction dispatch by MODE:
//   MODE 0 (VPU)      → EXEC_VPU   → WAIT_COMPUTE (until vpu_done)
//   MODE 1 (Systolic) → EXEC_SYS   → WAIT_COMPUTE (until systolic_done)
//   MODE 2 (TMA)      → EXEC_TMA   → WAIT_TMA    (until tma_done)
//   MODE 3 (HALT)     → HALT_STATE → done=1
//////////////////////////////////////////////////////////////////////////////////

module tensorcore #(
    parameter N = 4,
    parameter ADDR_WIDTH = 13,
    parameter DATA_WIDTH = 32,

    // VPU-specific params
    parameter VPU_DATA_W  = 32,
    parameter VPU_ADDR_W  = 13,
    parameter VPU_OP_W    = 4,
    parameter VPU_IADDR_W = 5,
    parameter COMP_DATA_WIDTH = 256,
    parameter MEM_LATENCY = 2
)(
    input  logic clk,
    input  logic rst_n,

    // High-level control
    input  logic start,
    output logic done,

    // I-RAM DMA interface (Port A of I_bram)
    input  logic        instr_write_en,
    input  logic [7:0]  iram_addr,
    input  logic [63:0] dma_iram_din,

    // BRAM Port B Interface (for data access)
    output logic [ADDR_WIDTH-1:0]    bram_addr_b,
    output logic [COMP_DATA_WIDTH-1:0] bram_din_b,
    input  logic [COMP_DATA_WIDTH-1:0] bram_dout_b,
    output logic                     bram_en_b,
    output logic                     bram_we_b,

    // === TMA instruction port (to l2_tile via compute_tile and tpu.sv) ===
    output logic                     tma_req,       // 1-cycle pulse: trigger TMA transfer
    output logic                     tma_dir,       // 0=DM_TO_L2, 1=L2_TO_DM
    output logic [15:0]              tma_dm_base,   // device memory base address
    output logic [14:0]              tma_l2_base,   // L2 SRAM base address
    output logic [15:0]              tma_len,       // transfer length in words
    input  logic                     tma_done       // 1-cycle pulse: TMA transfer complete
);

    //---------------------------------------------
    // Internal Signals
    //---------------------------------------------

    // PC signals
    logic [7:0] pc_val;
    logic       pc_enable;
    logic       pc_load;
    logic [7:0] pc_load_val;

    // Decoder signals
    logic [63:0] current_instr;
    logic [22:0] len;
    logic [12:0] addr_a, addr_b, addr_out;
    logic [1:0]  mode;
    logic [2:0]  vpu_type, vreg_dst, vreg_a, vreg_b, vpu_opcode;
    logic        scalar_b;

    // TMA decoder fields
    logic        tma_dir_dec;
    logic [15:0] tma_dm_addr_dec;
    logic [14:0] tma_l2_addr_dec;
    logic [15:0] tma_len_dec;

    // Unit control
    logic start_systolic, start_vpu;
    logic systolic_done, vpu_done;

    // Arbitrated BRAM signals from units
    logic [ADDR_WIDTH-1:0]            systolic_addr, vpu_addr;
    logic [COMP_DATA_WIDTH-1:0]       systolic_din_b, vpu_din_b;
    logic [COMP_DATA_WIDTH-1:0]       systolic_dout_b, vpu_dout_b;
    logic                             systolic_en_b, vpu_en_b;
    logic                             systolic_we_b, vpu_we_b;

    //---------------------------------------------
    // FSM for Instruction Orchestration
    //---------------------------------------------
    typedef enum logic [3:0] {
        IDLE         = 4'd0,
        EXEC_COMPUTE = 4'd3,
        WAIT_COMPUTE = 4'd4,
        FETCH_1      = 4'd5,
        FETCH_2      = 4'd6,
        FETCH_3      = 4'd7,
        HALT_STATE   = 4'd8,
        EXEC_TMA     = 4'd9,   // TMA: latch params and issue tma_req
        WAIT_TMA     = 4'd10   // TMA: wait for tma_done
    } tc_state_t;

    tc_state_t state;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state        <= IDLE;
            done         <= 1'b0;
            start_systolic <= 1'b0;
            start_vpu    <= 1'b0;
            pc_load      <= 1'b0;
            pc_load_val  <= 8'd0;
            tma_req      <= 1'b0;
            tma_dir      <= 1'b0;
            tma_dm_base  <= 16'd0;
            tma_l2_base  <= 15'd0;
            tma_len      <= 16'd0;
        end else begin
            // Default pulse signals
            start_systolic <= 1'b0;
            start_vpu <= 1'b0;
            pc_load   <= 1'b0;
            done      <= 1'b0;
            tma_req   <= 1'b0;

            case (state)
                IDLE: begin
                    if (start) begin
                        pc_load <= 1'b1;
                        pc_load_val <= 8'd0;
                        state <= FETCH_1;
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
                                state <= WAIT_COMPUTE;
                            end
                            2'b01: begin // Systolic
                                start_systolic <= 1'b1;
                                state <= WAIT_COMPUTE;
                            end
                            2'b10: begin // TMA instruction
                                state <= EXEC_TMA;
                            end
                            default: state <= HALT_STATE;
                        endcase
                    end
                end

                WAIT_COMPUTE: begin
                    if (systolic_done || vpu_done) begin
                        state <= FETCH_1;
                    end
                end

                // TMA: latch decoded fields, pulse tma_req, go to WAIT_TMA
                EXEC_TMA: begin
                    tma_req     <= 1'b1;
                    tma_dir     <= tma_dir_dec;
                    tma_dm_base <= tma_dm_addr_dec;
                    tma_l2_base <= tma_l2_addr_dec;
                    tma_len     <= tma_len_dec;
                    state       <= WAIT_TMA;
                end

                // TMA: wait for tma_done, then fetch next instruction
                WAIT_TMA: begin
                    tma_req <= 1'b0; // ensure req is a pulse
                    if (tma_done)
                        state <= FETCH_1;
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

    // Increment PC only after the current instruction has fully completed execution
    // to ensure combinational decoders provide stable fields to execution units.
    assign pc_enable = (state == WAIT_COMPUTE && ((mode == 2'b00 && vpu_done) || (mode == 2'b01 && systolic_done))) ||
                       (state == WAIT_TMA && tma_done);

    //---------------------------------------------
    // Submodule Instantiations
    //---------------------------------------------

    // PC: Program Counter
    pc #(
        .PC_WIDTH(8)
    ) u_pc (
        .clk(clk),
        .rst_n(rst_n),
        .PC_enable(pc_enable),
        .PC_load(pc_load),
        .PC_load_val(pc_load_val),
        .PC(pc_val)
    );

    // I_bram: Instruction BRAM
    blk_mem_gen_1 I_bram (
        .clka(clk),
        .ena(1'b1),
        .wea(instr_write_en),
        .addra(iram_addr),
        .dina(dma_iram_din),
        .douta(),

        .clkb(clk),
        .enb(1'b1),
        .web(1'b0),
        .addrb(pc_val),
        .dinb(64'b0),
        .doutb(current_instr)
    );

    // Decoder: Instruction Decoder
    decoder u_decoder (
        .instr_decode(current_instr),
        .len_decode(len),
        .addr_a_decode(addr_a),
        .addr_b_decode(addr_b),
        .addr_out_decode(addr_out),
        .mode_decode(mode),
        .vpu_type_decode(vpu_type),
        .vreg_dst_decode(vreg_dst),
        .vreg_a_decode(vreg_a),
        .vreg_b_decode(vreg_b),
        .vpu_opcode_decode(vpu_opcode),
        .scalar_b_decode(scalar_b),
        .tma_dir_decode(tma_dir_dec),
        .tma_dm_addr_decode(tma_dm_addr_dec),
        .tma_l2_addr_decode(tma_l2_addr_dec),
        .tma_len_decode(tma_len_dec)
    );

    // MXU: Matrix Unit
    mxu #(
        .N(N),
        .DATA_WIDTH(DATA_WIDTH),
        .BANKING_FACTOR(8),
        .ADDRESS_WIDTH(ADDR_WIDTH),
        .MEM_LATENCY(MEM_LATENCY),
        .COMP_DATA_WIDTH(COMP_DATA_WIDTH)
    ) u_mxu (
        .clk(clk),
        .rst_n(rst_n),
        .start(start_systolic),
        .done(systolic_done),
        .base_addr_w(addr_a),
        .base_addr_x(addr_b),
        .base_addr_out(addr_out),
        .mem_req_addr(systolic_addr),
        .mem_req_data(systolic_din_b),
        .mem_resp_data(systolic_dout_b),
        .mem_read_en (systolic_en_b),
        .mem_write_en(systolic_we_b)
    );

    // VPU SIMD
    vpu_simd #(
        .DATA_W(VPU_DATA_W),
        .ADDR_W(VPU_ADDR_W),
        .NUM_LANES(8),
        .COMP_DATA_WIDTH(COMP_DATA_WIDTH)
    ) u_vpu_simd (
        .clk(clk),
        .rst_n(rst_n),
        .start(start_vpu),
        .addr_a(addr_a),
        .addr_b(addr_b),
        .addr_out(addr_out),
        .vpu_type(vpu_type),
        .vreg_dst(vreg_dst),
        .vreg_a(vreg_a),
        .vreg_b(vreg_b),
        .vpu_opcode(vpu_opcode),
        .scalar_b(scalar_b),
        .bram_addr(vpu_addr),
        .bram_din(vpu_din_b),
        .bram_dout(vpu_dout_b),
        .bram_en(vpu_en_b),
        .bram_we(vpu_we_b),
        .done(vpu_done)
    );


    //---------------------------------------------
    // BRAM Port B Arbitration
    //---------------------------------------------
    always_comb begin
        bram_addr_b = '0;
        bram_din_b  = '0;
        bram_en_b   = 1'b0;
        bram_we_b   = 1'b0;

        systolic_dout_b  = bram_dout_b;
        vpu_dout_b       = bram_dout_b;

        case (mode)
            2'b00: begin  // VPU
                bram_addr_b = vpu_addr;
                bram_din_b  = vpu_din_b;
                bram_en_b   = vpu_en_b;
                bram_we_b   = vpu_we_b;
            end
            2'b01: begin  // Systolic
                bram_addr_b = systolic_addr;
                bram_din_b  = systolic_din_b;
                bram_en_b   = systolic_en_b;
                bram_we_b   = systolic_we_b;
            end
            default: ;
        endcase
    end

endmodule
