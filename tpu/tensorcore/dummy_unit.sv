`timescale 1ns / 1ps

// Bank-parallel vector add unit.
//
// The previous implementation walked one scalar word at a time through a shim
// in compute_core. That kept the old VADD behavior correct, but it did not
// exercise the 8-bank L1 datapath. This version reads and writes one 8-word
// row per loop iteration through the wide compute port.

module dummy_unit #(
    parameter ADDR_WIDTH = 13,
    parameter DATA_WIDTH = 32,
    parameter NUM_BANKS  = 8
)(
    input  logic                             clk,
    input  logic                             rst_n,
    input  logic                             start,
    input  logic [ADDR_WIDTH-1:0]            addr_a_vadd,
    input  logic [ADDR_WIDTH-1:0]            addr_b_vadd,
    input  logic [ADDR_WIDTH-1:0]            addr_out_vadd,
    input  logic [22:0]                      len_vadd,
    output logic                             done,

    // Wide BRAM Port B interface: one row contains NUM_BANKS words.
    output logic [ADDR_WIDTH-1:0]            bram_addr_b,
    output logic [NUM_BANKS*DATA_WIDTH-1:0]  bram_din_b,
    input  logic [NUM_BANKS*DATA_WIDTH-1:0]  bram_dout_b,
    output logic                             bram_en_b,
    output logic [NUM_BANKS-1:0]             bram_we_b
);

    typedef enum logic [2:0] {
        IDLE,
        READ_A,
        READ_B,
        WAIT_A,
        WAIT_B,
        WRITE_OUT,
        DONE
    } state_t;

    state_t state;

    logic [31:0] i;
    logic [NUM_BANKS-1:0][DATA_WIDTH-1:0] row_a;
    logic [NUM_BANKS-1:0][DATA_WIDTH-1:0] row_b;
    logic [NUM_BANKS-1:0][DATA_WIDTH-1:0] row_sum;
    logic [NUM_BANKS-1:0]                 write_mask;

    always_comb begin
        for (int lane = 0; lane < NUM_BANKS; lane++) begin
            row_sum[lane] = row_a[lane] + row_b[lane];
            write_mask[lane] = ((i + lane) < len_vadd);
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state       <= IDLE;
            done        <= 1'b0;
            i           <= '0;
            bram_en_b   <= 1'b0;
            bram_we_b   <= '0;
            bram_addr_b <= '0;
            bram_din_b  <= '0;
            row_a       <= '0;
            row_b       <= '0;
        end else begin
            done      <= 1'b0;
            bram_we_b <= '0;
            bram_en_b <= 1'b0;

            case (state)
                IDLE: begin
                    if (start) begin
                        i     <= 0;
                        state <= (len_vadd == 0) ? DONE : READ_A;
                    end
                end

                READ_A: begin
                    bram_en_b   <= 1'b1;
                    bram_addr_b <= addr_a_vadd + i[ADDR_WIDTH-1:0];
                    state       <= READ_B;
                end

                READ_B: begin
                    bram_en_b   <= 1'b1;
                    bram_addr_b <= addr_b_vadd + i[ADDR_WIDTH-1:0];
                    state       <= WAIT_A;
                end

                WAIT_A: begin
                    for (int lane = 0; lane < NUM_BANKS; lane++) begin
                        row_a[lane] <= bram_dout_b[lane*DATA_WIDTH +: DATA_WIDTH];
                    end
                    state <= WAIT_B;
                end

                WAIT_B: begin
                    for (int lane = 0; lane < NUM_BANKS; lane++) begin
                        row_b[lane] <= bram_dout_b[lane*DATA_WIDTH +: DATA_WIDTH];
                    end
                    state <= WRITE_OUT;
                end

                WRITE_OUT: begin
                    bram_en_b   <= 1'b1;
                    bram_we_b   <= write_mask;
                    bram_addr_b <= addr_out_vadd + i[ADDR_WIDTH-1:0];
                    for (int lane = 0; lane < NUM_BANKS; lane++) begin
                        bram_din_b[lane*DATA_WIDTH +: DATA_WIDTH] <= row_sum[lane];
                    end

                    if (i + NUM_BANKS >= len_vadd) begin
                        state <= DONE;
                    end else begin
                        i     <= i + NUM_BANKS;
                        state <= READ_A;
                    end
                end

                DONE: begin
                    done  <= 1'b1;
                    state <= IDLE;
                end

                default: begin
                    state <= IDLE;
                end
            endcase
        end
    end

endmodule
