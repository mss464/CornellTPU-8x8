// -----------------------------------------------------------------------------
// Matrix Unit (MXU) - Systolic Array Wrapper
// -----------------------------------------------------------------------------
// Hi hey
// Parameters:
//  - N: The size of the systolic array. Assume matrices are square and NxN.
//  - DATA_WIDTH: The size of each matrix element in bits.
//  - BANKING_FACTOR: How many elements can be loaded in (or later, stored) at once.
//                   BANKING_FACTOR * DATA_WIDTH should be the bandwidth of the 
//                   data connection with memory.
//  - ADDRESS_WIDTH: The size in bits of each memory address.
//  - MEM_LATENCY: The response latency of memory. Assume a fixed latency.
//  - COMP_DATA_WIDTH: Compute bus width (256 bits for 8 banks)
// -----------------------------------------------------------------------------

module mxu #(
    parameter int N = 4,
    parameter int DATA_WIDTH = 32,
    parameter int BANKING_FACTOR = 8,
    parameter int ADDRESS_WIDTH = 13,
    parameter int MEM_LATENCY = 2,
    parameter int COMP_DATA_WIDTH = 256
)(
    // --- Control Signals (Standard) ---
    input  logic clk,   // Clock signal
    input  logic rst_n, // Reset signal (active low, corresponds to "rst" pulse high in docs)

    // --- To/from control ---
    input  logic start, // Pulse high to begin mxu operation (load->matmul->store sequence)
    output logic done,  // Pulsed high by mxu when storing is complete

    // Base addresses (latched when start is driven high):
    input logic [ADDRESS_WIDTH-1:0] base_addr_w,   // Base address of weight matrix
    input logic [ADDRESS_WIDTH-1:0] base_addr_x,   // Base address of x matrix
    input logic [ADDRESS_WIDTH-1:0] base_addr_out, // Base address to store output matrix

    // --- To/from memory ---
    // mem_req_addr: Address of memory access request
    output logic [ADDRESS_WIDTH-1:0] mem_req_addr,
    // mem_req_data: Data of memory access request (meaningless for reads; data to write for writes)
    output logic [COMP_DATA_WIDTH-1 : 0] mem_req_data,
    // mem_resp_data: Data of memory access response (meaningless for writes; requested data for reads)
    input  logic [COMP_DATA_WIDTH-1 : 0] mem_resp_data,
    // mem_read_en: Memory read enable. Driven high when a memory read request is sent.
    output logic mem_read_en,
    // mem_write_en: Memory write enable. Driven high when a memory write request is sent.
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

    // Registers to latch matrix addresses
    logic [ADDRESS_WIDTH-1:0] base_addr_x_reg, base_addr_w_reg, base_addr_out_reg;

    // Index for load progress (indexes loading rows)
    logic [5:0] load_idx;  // Changed from integer for better synthesis/sim compatibility
    wire [ADDRESS_WIDTH-1:0] load_idx_addr =
        {{(ADDRESS_WIDTH-$bits(load_idx)){1'b0}}, load_idx};

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

    // -------------------------------------------------------------------------
    // Finite State Machine (FSM)
    // -------------------------------------------------------------------------
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
                        // Load full row of W: BRAM[addr] contains weight[load_idx][0:N-1]
                        for (int i = 0; i < N; i++) begin
                            weight_matrix[load_idx*N + i] <= mem_resp_data[i*DATA_WIDTH +: DATA_WIDTH];
                        end
                        if (load_idx >= N - 1) begin
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
                        // Load full row of X: BRAM[addr] contains X[load_idx][0:N-1]
                        for (int i = 0; i < N; i++) begin
                            x_matrix[load_idx*N + i] <= mem_resp_data[i*DATA_WIDTH +: DATA_WIDTH];
                        end
                        if (load_idx >= N - 1) begin
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

                    // ---- Weight pipeline: Loading Column-i weights into systolic array ----
                    // The systolic array (systolic.sv) expects weights loaded from the top.
                    // If we load Row 0, then Row 1, Row 1 pushes Row 0 down.
                    // At the end, PE3j (bottom) will have the FIRST row loaded.
                    // To have Row 0 in PE0j (top), we must load Row 3, 2, 1, 0.
                    
                    // Column 0
                    if (phase_counter < N) begin
                        sys_weight_in_11 <= weight_matrix[0*N + (N-1-phase_counter)];
                        sys_accept_w_1   <= 1;
                    end else sys_accept_w_1 <= 0;

                    // Column 1
                    if (phase_counter >= 1 && phase_counter < N+1) begin
                        sys_weight_in_12 <= weight_matrix[1*N + (N-1-(phase_counter-1))];
                        sys_accept_w_2   <= 1;
                    end else sys_accept_w_2 <= 0;

                    // Column 2
                    if (phase_counter >= 2 && phase_counter < N+2) begin
                        sys_weight_in_13 <= weight_matrix[2*N + (N-1-(phase_counter-2))];
                        sys_accept_w_3   <= 1;
                    end else sys_accept_w_3 <= 0;

                    // Column 3
                    if (phase_counter >= 3 && phase_counter < N+3) begin
                        sys_weight_in_14 <= weight_matrix[3*N + (N-1-(phase_counter-3))];
                        sys_accept_w_4   <= 1;
                    end else sys_accept_w_4 <= 0;

                    // ---- Switch X input (Cycle N+3 for full weight promotion and switch) ----
                    if (phase_counter == N+3)
                        sys_switch_in <= 1;
                    else
                        sys_switch_in <= 0;

                    // ---- X input stream: X[row][col] ----
                    // Elements of row i are fed column 0, then 1, 2, 3.
                    // Staggered: row i starts at cycle N+4 + i
                    for (int row = 0; row < N; row++) begin
                        int ph;
                        ph = int'(phase_counter) - (N + 4 + row);
                        if (ph >= 0 && ph < N) begin
                            case (row)
                                0: begin sys_start_1 <= 1; sys_data_in_11 <= x_matrix[ph*N + 0]; end
                                1: begin sys_start_2 <= 1; sys_data_in_21 <= x_matrix[ph*N + 1]; end
                                2: begin sys_start_3 <= 1; sys_data_in_31 <= x_matrix[ph*N + 2]; end
                                3: begin sys_start_4 <= 1; sys_data_in_41 <= x_matrix[ph*N + 3]; end
                            endcase
                        end
                    end

                    // ---- Stop when all sequences done ----
                    if (phase_counter >= 5*N) begin
                        phase_counter <= '0;
                        state <= S_CAPTURE;
                    end
                end

                S_CAPTURE: begin
                    bit all_done;
                    all_done = 1;
                    for (int i = 0; i < N; i++)
                        all_done &= (row_ptr[i] == N);

                    phase_counter <= phase_counter + 1;

                    // Stop if all done OR if watchdog expires (e.g. 64 cycles)
                    if (all_done || phase_counter[5]) begin
                        phase_counter <= 0;
                        state <= S_STORE_REQ;
                    end
                end

                S_STORE_REQ: begin
                    mem_req_addr <= base_addr_out_reg + load_idx_addr;

                    // Write out_matrix[load_idx][0:N-1] as a single 256-bit word
                    for (int i = 0; i < N; i++) begin
                        mem_req_data[i*DATA_WIDTH +: DATA_WIDTH] <= out_matrix[load_idx*N + i];
                    end
                    // Fill remaining upper bits with 0s
                    for (int i = N; i < BANKING_FACTOR; i++) begin
                        mem_req_data[i*DATA_WIDTH +: DATA_WIDTH] <= '0;
                    end

                    mem_write_en <= 1;
                    mem_latency_timer <= '0;
                    state <= S_STORE_WAIT;
                end

                S_STORE_WAIT: begin
                    if (mem_latency_timer >= (MEM_LATENCY - 1)) begin
                        if (load_idx >= N - 1) begin
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
