// ALU-style VPU operations
module vpu_op #(
  parameter int DATA_W = 32,
  parameter int OP_W = 10
)(
  input logic start,
  input logic [DATA_W-1:0] operand0,
  input logic [DATA_W-1:0] operand1,
  input logic [OP_W-1:0] opcode,
  output logic [DATA_W-1:0] result_out
);

// localparams for states
localparam logic [OP_W-1:0] ADD = OP_W'(0);
localparam logic [OP_W-1:0] SUB = OP_W'(1);
localparam logic [OP_W-1:0] RELU = OP_W'(2);
localparam logic [OP_W-1:0] MUL = OP_W'(3);
localparam logic [OP_W-1:0] D_RELU = OP_W'(4); // relu deriv for backward pass

// internal signalas for computation result storing
logic [DATA_W-1:0] result;
logic [DATA_W-1:0] adder_a, adder_b;
logic [DATA_W-1:0] adder_result;
logic [DATA_W-1:0] relu_result;
logic [DATA_W-1:0] d_relu_result;
logic [DATA_W-1:0] mul_a, mul_b;
logic [DATA_W-1:0] mul_result;

// fp32 adder instance ; this can be adjusted for fxp
logic [DATA_W-1:0] operand1_neg;
assign operand1_neg = {~operand1[DATA_W-1], operand1[DATA_W-2:0]};

assign adder_a = operand0;
assign adder_b = (opcode == SUB) ? operand1_neg : operand1;
fp32_add #(.FORMAT("FP32")) fp32_adder (
  .a(adder_a),
  .b(adder_b),
  .result(adder_result)
);

assign mul_a = operand0;
assign mul_b = operand1;

fp32_mul #(.FORMAT("FP32")) fp32_multiplier (
  .a(mul_a),
  .b(mul_b),
  .result(mul_result)
);

// ReLU operation 
always_comb begin
  relu_result = {DATA_W{1'b0}};
  if (!operand0[DATA_W-1]) begin
    relu_result = operand0;
  end
end

// ReLU deriv
always_comb begin
  d_relu_result = 32'h3f800000; // 1.0 in fp32
  if (operand0[DATA_W-1] || operand0 == 32'h00000000) begin
    d_relu_result = '0;
  end
end

// opcode decoding + proper operation
always_comb begin
    case (opcode)
      ADD: begin
        result = adder_result;
      end
      SUB: begin
        result = adder_result;
      end
      RELU: begin
        result = relu_result;
      end
      MUL: begin
        result = mul_result;
      end
      D_RELU: begin
        result = d_relu_result;
      end
      default: begin
        result = {DATA_W{1'b0}};
      end
    endcase
end

assign result_out = result;

endmodule
