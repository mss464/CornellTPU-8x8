`timescale 1ns/1ps
//////////////////////////////////////////////////////////////////////////////////
// mxu.sv - Matrix Unit (Systolic Array Wrapper)
//
// Portable across FPGA and ASIC targets:
//   - Define TARGET_FPGA for FPGA-optimized constructs
//   - Default (no define) uses ASIC-compatible constructs
//////////////////////////////////////////////////////////////////////////////////

module mxu #(
`ifdef TARGET_FPGA
    parameter int N = 4,
    parameter int DATA_WIDTH = 32,
    parameter int BANKING_FACTOR = 1,
    parameter int ADDRESS_WIDTH = 13,
    parameter int MEM_LATENCY = 3
`else
    // ASIC: Use integer for broader tool compatibility
    parameter N = 4,
    parameter DATA_WIDTH = 32,
    parameter BANKING_FACTOR = 1,
    parameter ADDRESS_WIDTH = 13,
    parameter MEM_LATENCY = 3
`endif
)(
    input  logic clk,
    input  logic rst_n,

    // To/from control:
    input  logic start,
    output logic done,

    input logic [ADDRESS_WIDTH-1:0] base_addr_w,
    input logic [ADDRESS_WIDTH-1:0] base_addr_x,
    input logic [ADDRESS_WIDTH-1:0] base_addr_out,

    // To/from memory:
    output logic [ADDRESS_WIDTH-1:0] mem_req_addr,
    output logic [BANKING_FACTOR*DATA_WIDTH-1 : 0] mem_req_data,
    input  logic [BANKING_FACTOR*DATA_WIDTH-1 : 0] mem_resp_data,
    output logic mem_read_en,
    output logic mem_write_en
);

    // Temporary (for debugging and facilitating Cocotb testbench):
    logic signed [DATA_WIDTH-1:0] out_matrix [N*N-1:0];

    // Index helper: row-major layout (r*N + c)
    // Using inline expressions for ASIC tool compatibility

    // Local buffer memory for W and X matrices
    logic signed [DATA_WIDTH-1:0] weight_matrix [N*N-1:0];
    logic signed [DATA_WIDTH-1:0] x_matrix [N*N-1:0];

    localparam int TOTAL_ELEMS = N*N;
    localparam int BYTES_PER_BEAT = BANKING_FACTOR * (DATA_WIDTH / 8);

    // Registers to latch matrix addresses
    logic [ADDRESS_WIDTH-1:0] base_addr_x_reg, base_addr_w_reg, base_addr_out_reg;

    // Index for load progress (indexes loading beats)
    logic [5:0] load_idx;  // Changed from integer for better synthesis/sim compatibility
    wire [ADDRESS_WIDTH-1:0] load_idx_addr =
        {{(ADDRESS_WIDTH-$bits(load_idx)){1'b0}}, load_idx} * BANKING_FACTOR;

    // Timer for memory fixed latency
    logic [$clog2(MEM_LATENCY+1)-1:0] mem_latency_timer;

    // X and W matrix elements for input into array
    logic signed [DATA_WIDTH-1:0]
        sys_weight_in_11, sys_weight_in_12, sys_weight_in_13, sys_weight_in_14,
        sys_data_in_11,   sys_data_in_21,   sys_data_in_31,   sys_data_in_41;
    // Control signals
    logic
        sys_accept_w_1, sys_accept_w_2, sys_accept_w_3, sys_accept_w_4,
        sys_start_1, sys_start_2, sys_start_3, sys_start_4,
        sys_switch_in;
    // Output matrix elements
    logic signed [DATA_WIDTH-1:0]
        sys_data_out_41, sys_data_out_42, sys_data_out_43, sys_data_out_44;
    // Status signals
    logic
        sys_valid_out_41, sys_valid_out_42, sys_valid_out_43, sys_valid_out_44;

    logic [31:0] ub_rd_col_size_in = 32'd0;
    logic ub_rd_col_size_valid_in  = 1'b0;

    systolic array (
        .clk(clk),
        .rst_n(rst_n),

        .sys_data_in_11(sys_data_in_11),
        .sys_data_in_21(sys_data_in_21),
        .sys_data_in_31(sys_data_in_31),
        .sys_data_in_41(sys_data_in_41),
        .sys_start_1(sys_start_1),
        .sys_start_2(sys_start_2),
        .sys_start_3(sys_start_3),
        .sys_start_4(sys_start_4),
        .sys_data_out_41(sys_data_out_41),
        .sys_data_out_42(sys_data_out_42),
        .sys_data_out_43(sys_data_out_43),
        .sys_data_out_44(sys_data_out_44),
        .sys_valid_out_41(sys_valid_out_41),
        .sys_valid_out_42(sys_valid_out_42),
        .sys_valid_out_43(sys_valid_out_43),
        .sys_valid_out_44(sys_valid_out_44),
        .sys_weight_in_11(sys_weight_in_11),
        .sys_weight_in_12(sys_weight_in_12),
        .sys_weight_in_13(sys_weight_in_13),
        .sys_weight_in_14(sys_weight_in_14),
        .sys_accept_w_1(sys_accept_w_1),
        .sys_accept_w_2(sys_accept_w_2),
        .sys_accept_w_3(sys_accept_w_3),
        .sys_accept_w_4(sys_accept_w_4),
        .sys_switch_in(sys_switch_in),
        .ub_rd_col_size_in(ub_rd_col_size_in),
        .ub_rd_col_size_valid_in(ub_rd_col_size_valid_in)
    );

    typedef enum logic [3:0] {
        S_IDLE,
        S_LOAD_W_REQ,
        S_LOAD_W_WAIT,
        S_LOAD_X_REQ,
        S_LOAD_X_WAIT,
        S_RUN,
        S_CAPTURE,
        S_STORE_REQ,
        S_STORE_WAIT,
        S_DONE
    } state_t;

    state_t state;
    logic [$clog2(8*N):0] phase_counter;
    logic [3:0] row_ptr [N];  // Changed from integer for better Icarus compatibility

    // Collect outputs from systolic array when valid out signals asserted
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int i=0; i<N; i++) row_ptr[i] <= 0;
            for (int r=0; r<N; r++)
                for (int c=0; c<N; c++)
                    out_matrix[(r*N + c)] <= '0;
        end else begin
        
            if (start) begin
                // CRITICAL: Clear row pointers and output matrix on new computation
                for (int i=0; i<N; i++) row_ptr[i] <= 0;
                for (int r=0; r<N; r++)
                    for (int c=0; c<N; c++)
                        out_matrix[(r*N + c)] <= '0;
            end else begin
        
            if (sys_valid_out_41 && row_ptr[0] < N) begin
                out_matrix[row_ptr[0]*N + 0] <= sys_data_out_41;
                row_ptr[0] <= row_ptr[0] + 1;
            end
            if (sys_valid_out_42 && row_ptr[1] < N) begin
                out_matrix[row_ptr[1]*N + 1] <= sys_data_out_42;
                row_ptr[1] <= row_ptr[1] + 1;
            end
            if (sys_valid_out_43 && row_ptr[2] < N) begin
                out_matrix[row_ptr[2]*N + 2] <= sys_data_out_43;
                row_ptr[2] <= row_ptr[2] + 1;
            end
            if (sys_valid_out_44 && row_ptr[3] < N) begin
                out_matrix[row_ptr[3]*N + 3] <= sys_data_out_44;
                row_ptr[3] <= row_ptr[3] + 1;
            end
            
            end
        end
    end

    // FSM Logic
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            // Return to idle state
            state <= S_IDLE;

            // Reset run state counter
            phase_counter <= '0;

            mem_req_addr <= '0;
            mem_req_data <= '0;
            mem_read_en <= 0;
            mem_write_en <= 0;

            mem_latency_timer <= '0;

            load_idx <= 0;

            done <= 0;

            // Reset latched base addresses
            base_addr_x_reg <= '0;
            base_addr_w_reg <= '0;
            base_addr_out_reg <= '0;

            // **CRITICAL FIX**: Clear weight and x matrix buffers on reset
            for (int i=0; i<N*N; i++) begin
                weight_matrix[i] <= '0;
                x_matrix[i] <= '0;
            end

            // Datapath control signals
            sys_accept_w_1 <= 0;
            sys_accept_w_2 <= 0;
            sys_accept_w_3 <= 0;
            sys_accept_w_4 <= 0;
            sys_start_1 <= 0;
            sys_start_2 <= 0;
            sys_start_3 <= 0;
            sys_start_4 <= 0;
            sys_switch_in <= 0;
            sys_weight_in_11 <= '0;
            sys_weight_in_12 <= '0;
            sys_weight_in_13 <= '0;
            sys_weight_in_14 <= '0;
            sys_data_in_11 <= '0;
            sys_data_in_21 <= '0;
            sys_data_in_31 <= '0;
            sys_data_in_41 <= '0;
        end else begin
            // Defaults
            done <= 0;
            // Datapath control signals
            sys_accept_w_1 <= 0;
            sys_accept_w_2 <= 0;
            sys_accept_w_3 <= 0;
            sys_accept_w_4 <= 0;
            sys_start_1 <= 0;
            sys_start_2 <= 0;
            sys_start_3 <= 0;
            sys_start_4 <= 0;
            sys_switch_in <= 0;
            sys_weight_in_11 <= '0;
            sys_weight_in_12 <= '0;
            sys_weight_in_13 <= '0;
            sys_weight_in_14 <= '0;
            sys_data_in_11 <= '0;
            sys_data_in_21 <= '0;
            sys_data_in_31 <= '0;
            sys_data_in_41 <= '0;

            mem_req_addr <= '0;
            mem_req_data <= '0;
            mem_read_en <= 0;
            mem_write_en <= 0;

            case(state)
                S_IDLE: begin
                    if (start) begin
                        base_addr_x_reg <= base_addr_x;
                        base_addr_w_reg <= base_addr_w;
                        base_addr_out_reg <= base_addr_out;
                        
                        state <= S_LOAD_W_REQ;
                    end
                end

                S_LOAD_W_REQ: begin
                    mem_req_addr <= base_addr_w_reg + load_idx_addr;
                    mem_read_en <= 1;
                    mem_latency_timer <= '0;
                    state <= S_LOAD_W_WAIT;
                end

                S_LOAD_W_WAIT: begin
                    if (mem_latency_timer >= (MEM_LATENCY - 1)) begin
                        for (int b = 0; b < BANKING_FACTOR; b++) begin
                            int flat_index;
                            flat_index = load_idx * BANKING_FACTOR + b;
                            if (flat_index < TOTAL_ELEMS) begin
                                weight_matrix[flat_index] <= mem_resp_data[b*DATA_WIDTH +: DATA_WIDTH];
                            end
                        end
                        if ((int'(load_idx) + 1) * BANKING_FACTOR >= TOTAL_ELEMS) begin
                            load_idx <= '0;
                            state <= S_LOAD_X_REQ;
                        end else begin
                            load_idx <= load_idx + 1;
                            state <= S_LOAD_W_REQ;
                        end
                    end else begin
                        mem_latency_timer <= mem_latency_timer + 1;
                    end
                end

                S_LOAD_X_REQ: begin
                    mem_req_addr <= base_addr_x_reg + load_idx_addr;
                    mem_read_en <= 1;
                    mem_latency_timer <= '0;
                    state <= S_LOAD_X_WAIT;
                end

                S_LOAD_X_WAIT: begin
                    if (mem_latency_timer >= (MEM_LATENCY - 1)) begin
                        for (int b = 0; b < BANKING_FACTOR; b++) begin
                            int flat_index;
                            flat_index = load_idx * BANKING_FACTOR + b;
                            if (flat_index < TOTAL_ELEMS) begin
                                x_matrix[flat_index] <= mem_resp_data[b*DATA_WIDTH +: DATA_WIDTH];
                            end
                        end
                        if ((int'(load_idx) + 1) * BANKING_FACTOR >= TOTAL_ELEMS) begin
                            load_idx <= '0;
                            phase_counter <= '0;
                            state <= S_RUN;
                        end else begin
                            load_idx <= load_idx + 1;
                            state <= S_LOAD_X_REQ;
                        end
                    end else begin
                        mem_latency_timer <= mem_latency_timer + 1;
                    end
                end
                
                S_RUN: begin
                    // Increment phase counter
                    phase_counter <= phase_counter + 1;

                    // ---- Weight pipeline: column-major, reversed along rows ----
                    // Column 0
                    if (phase_counter < N) begin
                        sys_weight_in_11 <= weight_matrix[(0*N + N-1-phase_counter)];
                        sys_accept_w_1   <= 1;
                    end else sys_accept_w_1 <= 0;

                    // Column 1
                    if (phase_counter >= 1 && phase_counter < N+1) begin
                        sys_weight_in_12 <= weight_matrix[(1*N + N-1-(phase_counter-1))];
                        sys_accept_w_2   <= 1;
                    end else sys_accept_w_2 <= 0;

                    // Column 2
                    if (phase_counter >= 2 && phase_counter < N+2) begin
                        sys_weight_in_13 <= weight_matrix[(2*N + N-1-(phase_counter-2))];
                        sys_accept_w_3   <= 1;
                    end else sys_accept_w_3 <= 0;

                    // Column 3
                    if (phase_counter >= 3 && phase_counter < N+3) begin
                        sys_weight_in_14 <= weight_matrix[(3*N + N-1-(phase_counter-3))];
                        sys_accept_w_4   <= 1;
                    end else sys_accept_w_4 <= 0;

                    // ---- Switch X input when last weight of column 1 is loaded ----
                    if (phase_counter == N-1)
                        sys_switch_in <= 1;
                    else
                        sys_switch_in <= 0;

                    // ---- X input stream: staggered along rows ----
                    // Each PE row gets a different column of X
                    for (int row = 0; row < N; row++) begin
                        int ph;
                        ph = int'(phase_counter) - (N + row);
                        if (ph >= 0 && ph < N) begin
                            case (row)
                                0: begin sys_start_1 <= 1; sys_data_in_11 <= x_matrix[(ph*N + 0)]; end
                                1: begin sys_start_2 <= 1; sys_data_in_21 <= x_matrix[(ph*N + 1)]; end
                                2: begin sys_start_3 <= 1; sys_data_in_31 <= x_matrix[(ph*N + 2)]; end
                                3: begin sys_start_4 <= 1; sys_data_in_41 <= x_matrix[(ph*N + 3)]; end
                            endcase
                        end
                    end

                    // ---- Stop when weight and input sequences done ----
                    if (phase_counter >= 3*N - 2) begin
                        phase_counter <= '0;
                        state <= S_CAPTURE;
                    end
                end

                S_CAPTURE: begin
                    bit all_done;
                    all_done = 1;
                    for (int i = 0; i < N; i++)
                        all_done &= (row_ptr[i] == N);
                    if (all_done)
                        state <= S_STORE_REQ;
                end

                S_STORE_REQ: begin
                    mem_req_addr <= base_addr_out_reg + load_idx_addr;

                    for (int b = 0; b < BANKING_FACTOR; b++) begin
                        int flat_index;
                        flat_index = load_idx * BANKING_FACTOR + b;
                        if (flat_index < TOTAL_ELEMS)
                            mem_req_data[b*DATA_WIDTH +: DATA_WIDTH] <= out_matrix[flat_index];
                        else
                            mem_req_data[b*DATA_WIDTH +: DATA_WIDTH] <= '0;
                    end

                    mem_write_en <= 1;
                    mem_latency_timer <= '0;
                    state <= S_STORE_WAIT;
                end

                S_STORE_WAIT: begin
                    if (mem_latency_timer >= (MEM_LATENCY - 1)) begin
                        if ((int'(load_idx) + 1) * BANKING_FACTOR >= TOTAL_ELEMS) begin
                            state <= S_DONE;
                        end else begin
                            load_idx <= load_idx + 1;
                            state <= S_STORE_REQ;
                        end
                    end else begin
                        mem_latency_timer <= mem_latency_timer + 1;
                    end
                end

                S_DONE: begin
                    done <= 1;
                    load_idx <= 0;
                    state <= S_IDLE;
                end
                default: begin
                    done <= 0;
                    mem_read_en <= 0;
                    mem_write_en <= 0;
                    state <= S_IDLE;
                end

            endcase
        end
    end

    // Temporary: Break out the out matrix for waveform debugging
    generate
    for (genvar i = 0; i < N*N; i++) begin : OUT_DEBUG
        logic signed [DATA_WIDTH-1:0] out_elem;
        assign out_elem = out_matrix[i];
    end
    endgenerate

endmodule
