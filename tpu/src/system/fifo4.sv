module fifo4 #(
    parameter int WIDTH = 32,
    parameter int DEPTH = 8   // Must be a power of 2
)(
    input  logic                 clk,
    input  logic                 rst_n,

    // Write side
    input  logic                 wr_en,
    input  logic [WIDTH-1:0]     wr_data,

    // Read side
    input  logic                 rd_en,
    output logic [WIDTH-1:0]     rd_data,

    // Status
    output logic                 full,
    output logic                 empty,
    output logic                 one_item_remaining
);

    localparam int PTR_W = $clog2(DEPTH) + 1;  // index bits + wrap bit

    //-----------------------------
    // Storage (DEPTH entries)
    //-----------------------------
    logic [WIDTH-1:0] mem [0:DEPTH-1];
    initial begin
        for (int i = 0; i < DEPTH; i++) mem[i] = '0;
    end

    //-----------------------------
    // Pointers (index bits + wrap bit)
    //-----------------------------
    logic [PTR_W-1:0] wptr;   // index = wptr[PTR_W-2:0], wrap = wptr[PTR_W-1]
    logic [PTR_W-1:0] rptr;

    //-----------------------------
    // EMPTY / FULL logic
    //-----------------------------
    assign empty = (wptr == rptr);
    assign full  = (wptr[PTR_W-1] != rptr[PTR_W-1]) &&
                   (wptr[PTR_W-2:0] == rptr[PTR_W-2:0]);
    assign one_item_remaining = ((rptr + 1'b1) == wptr);

    //-----------------------------
    // WRITE logic
    //-----------------------------
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            wptr <= '0;
        end else if (wr_en && !full) begin
            mem[wptr[PTR_W-2:0]] <= wr_data;
            wptr <= wptr + 1'b1;
        end
    end

    //-----------------------------
    // READ logic
    //-----------------------------
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            rptr <= '0;
            rd_data <= '0;
        end else if (rd_en && !empty) begin
            rd_data <= mem[rptr[PTR_W-2:0]];
            rptr <= rptr + 1'b1;
        end
    end

endmodule
