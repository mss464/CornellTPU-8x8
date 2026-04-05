`timescale 1 ns / 1 ps
// ============================================================================
// l2_ctrl.sv — L2↔L1 burst transfer sub-FSM
//
// L2 SRAM is 32-bit wide.  L1 BRAM DMA port is 256-bit wide (8 banks).
// This module packs/unpacks 8 × 32-bit L2 words ↔ one 256-bit L1 word.
//
// Handled modes:
//   7 = L22L1 — accumulate 8 × 32-bit L2 reads into 256-bit, write to L1
//   8 = L12L2 — read 256-bit from L1, write 8 × 32-bit words to L2
//
// length_in is in 32-bit words and MUST be a multiple of 8.
//
// BRAM timing: 1-cycle registered output.
//   L2 read: issue address cycle N → data valid cycle N+1.
//   L1 read: issue address cycle N → data valid cycle N+1.
// ============================================================================
module l2_ctrl (
    input  wire        clk,
    input  wire        rst_n,

    // Arbiter dispatch
    input  wire        start,
    input  wire [3:0]  mode,
    input  wire [14:0] addr_l2_in,
    input  wire [15:0] addr_l1_in,
    input  wire [31:0] length_in,      // length in 32-bit words (multiple of 8)
    output reg         done,

    // L2 tile Port A (32-bit)
    output reg  [14:0] l2_ct_addr,
    output reg         l2_ct_en,
    output reg         l2_ct_we,
    output reg [31:0]  l2_ct_din,
    input  wire [31:0] l2_ct_dout,

    // L1 DMA port (256-bit, via compute_tile)
    output reg          l1_dma_wr_en,
    output logic [255:0] l1_dma_wr_data,
    output reg  [15:0]  l1_dma_write_ptr,
    output reg          l1_dma_rd_en,
    input  wire [255:0] l1_dma_rd_data,
    output reg  [15:0]  l1_dma_read_ptr
);

    assign l1_dma_wr_data = pack_reg;

    localparam MODE_L22L1 = 4'd7;
    localparam MODE_L12L2 = 4'd8;

    // FSM states
    localparam [2:0] S_IDLE       = 3'd0,
                     S_L22L1_ISSUE = 3'd1,  // issue L2 reads (8 per group)
                     S_L22L1_WR   = 3'd2,   // write packed word to L1
                     S_L12L2_WAIT = 3'd3,   // wait for L1 read data
                     S_L12L2_WR   = 3'd4;   // write 8 words to L2

    reg [2:0]   state;
    reg [14:0]  latched_addr_l2;
    reg [15:0]  latched_length;    // in 32-bit words

    reg [15:0]  word_cnt;          // 32-bit words issued/written so far
    reg [2:0]   sub_cnt;           // 0–7 within current 256-bit group
    reg [15:0]  l1_addr;           // L1 word address (256-bit words)
    reg [255:0] pack_reg;          // packing / unpacking buffer

    // Pipeline delay for L2 read valid and its sub-index
    reg         prev_l2_rd;
    reg [2:0]   prev_sub_cnt;

    // Pipeline delay for L1 read valid
    reg         prev_l1_rd;

    // -------------------------------------------------------------------------
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state           <= S_IDLE;
            done            <= 1'b0;
            latched_addr_l2 <= 15'd0;
            latched_length  <= 16'd0;
            word_cnt        <= 16'd0;
            sub_cnt         <= 3'd0;
            l1_addr         <= 16'd0;
            pack_reg        <= 256'd0;
            prev_l2_rd      <= 1'b0;
            prev_sub_cnt    <= 3'd0;
            prev_l1_rd      <= 1'b0;
            l2_ct_addr      <= 15'd0;
            l2_ct_en        <= 1'b0;
            l2_ct_we        <= 1'b0;
            l2_ct_din       <= 32'd0;
            l1_dma_wr_en    <= 1'b0;
            l1_dma_write_ptr<= 16'd0;
            l1_dma_rd_en    <= 1'b0;
            l1_dma_read_ptr <= 16'd0;
        end else begin
            // Pulse defaults
            done           <= 1'b0;
            l2_ct_en       <= 1'b0;
            l2_ct_we       <= 1'b0;
            l1_dma_wr_en   <= 1'b0;
            l1_dma_rd_en   <= 1'b0;

            // Pipeline tracking
            prev_l2_rd     <= (l2_ct_en && !l2_ct_we);  // was a read issued last cycle?
            prev_sub_cnt   <= sub_cnt;
            prev_l1_rd     <= l1_dma_rd_en;

            // Capture L2 read data into pack register (1-cycle latency)
            if (prev_l2_rd) begin
                pack_reg[prev_sub_cnt*32 +: 32] <= l2_ct_dout;
            end

            case (state)
                // =============================================================
                S_IDLE: begin
                    if (start) begin
                        latched_addr_l2 <= addr_l2_in;
                        latched_length  <= length_in[15:0];
                        word_cnt        <= 16'd0;
                        sub_cnt         <= 3'd0;
                        l1_addr         <= addr_l1_in;
                        pack_reg        <= 256'd0;
                        case (mode)
                            MODE_L22L1: state <= S_L22L1_ISSUE;
                            MODE_L12L2: state <= S_L12L2_WAIT;
                            default:    done  <= 1'b1;
                        endcase
                    end
                end

                // =============================================================
                // L2→L1: Issue 8 L2 reads per group, capture into pack_reg
                // =============================================================
                S_L22L1_ISSUE: begin
                    if (word_cnt < latched_length) begin
                        // Issue L2 read for word_cnt
                        l2_ct_addr <= latched_addr_l2 + word_cnt[14:0];
                        l2_ct_en   <= 1'b1;
                        // l2_ct_we stays 0 (read)
                        sub_cnt    <= word_cnt[2:0];
                        word_cnt   <= word_cnt + 16'd1;

                        // After issuing word 7 (sub_cnt will be 7 next cycle),
                        // we must wait for the last capture then write L1.
                        if (word_cnt[2:0] == 3'd7) begin
                            state <= S_L22L1_WR;
                        end
                    end else begin
                        // Should not reach here if length is multiple of 8,
                        // but handle gracefully
                        state <= S_IDLE;
                        done  <= 1'b1;
                    end
                end

                // Wait for the last L2 read to land, then write packed word to L1
                S_L22L1_WR: begin
                    // prev_l2_rd will be 1 on the first cycle here (data for
                    // word 7 arriving). The capture into pack_reg happens above.
                    // We need one MORE cycle after capture to let the NBA settle.
                    if (prev_l2_rd && prev_sub_cnt == 3'd7) begin
                        // pack_reg has words 0-6 already; word 7 is being
                        // captured this cycle via the NBA above.  We must wait
                        // one more cycle for it to be committed.
                    end else if (!prev_l2_rd) begin
                        // All 8 words now in pack_reg — write to L1
                        l1_dma_wr_en    <= 1'b1;
                        l1_dma_write_ptr<= l1_addr;
                        l1_addr         <= l1_addr + 16'd1;

                        if (word_cnt >= latched_length) begin
                            state <= S_IDLE;
                            done  <= 1'b1;
                        end else begin
                            state <= S_L22L1_ISSUE;
                        end
                    end
                end

                // =============================================================
                // L1→L2: Read 256-bit from L1, unpack 8 × 32-bit to L2
                // =============================================================
                S_L12L2_WAIT: begin
                    if (prev_l1_rd) begin
                        // L1 data arrived
                        pack_reg <= l1_dma_rd_data;
                        sub_cnt  <= 3'd0;
                        state    <= S_L12L2_WR;
                    end else begin
                        // Issue L1 read
                        l1_dma_rd_en    <= 1'b1;
                        l1_dma_read_ptr <= l1_addr;
                    end
                end

                S_L12L2_WR: begin
                    // Write one 32-bit word per cycle to L2
                    l2_ct_addr <= latched_addr_l2 + word_cnt[14:0];
                    l2_ct_en   <= 1'b1;
                    l2_ct_we   <= 1'b1;
                    l2_ct_din  <= pack_reg[sub_cnt*32 +: 32];

                    word_cnt   <= word_cnt + 16'd1;
                    sub_cnt    <= sub_cnt + 3'd1;

                    if (sub_cnt == 3'd7) begin
                        // Finished this 256-bit word
                        l1_addr <= l1_addr + 16'd1;
                        if (word_cnt + 16'd1 >= latched_length) begin
                            state <= S_IDLE;
                            done  <= 1'b1;
                        end else begin
                            state <= S_L12L2_WAIT;
                        end
                    end
                end

                default: state <= S_IDLE;
            endcase
        end
    end

endmodule
