`timescale 1 ns / 1 ps
// ============================================================================
// compute_ctrl.sv — Compute dispatch sub-FSM (P2.08)
//
// Owns: compute_tile start/done handshake (mode 3 COMPUTE).
// Runs independently of dma_engine and l2_ctrl — all use different BRAM ports.
//
// Interface contract:
//   - `start` is a 1-cycle pulse from the tpu.sv arbiter.
//   - `done`  is a 1-cycle pulse on completion; arbiter clears compute_running.
// ============================================================================
module compute_ctrl (
    input  wire  clk,
    input  wire  rst_n,

    // Arbiter dispatch
    input  wire  start,           // 1-cycle pulse: begin compute execution
    output reg   done,            // 1-cycle pulse: compute_tile_done seen

    // Compute tile control
    output reg   start_compute_tile,
    input  wire  compute_tile_done
);

    localparam CC_IDLE    = 1'b0;
    localparam CC_RUNNING = 1'b1;

    reg state;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state              <= CC_IDLE;
            done               <= 1'b0;
            start_compute_tile <= 1'b0;
        end else begin
            // Pulse defaults
            done               <= 1'b0;
            start_compute_tile <= 1'b0;

            case (state)
                CC_IDLE: begin
                    if (start) begin
                        start_compute_tile <= 1'b1;
                        state              <= CC_RUNNING;
                    end
                end

                CC_RUNNING: begin
                    if (compute_tile_done) begin
                        state <= CC_IDLE;
                        done  <= 1'b1;
                    end
                end

                default: state <= CC_IDLE;
            endcase
        end
    end

endmodule
