"""Unit tests for vpu_op.sv - VPU ALU operations (ADD, SUB, RELU, MUL)"""

import cocotb
from cocotb.triggers import Timer
import struct
import random

# Opcodes from vpu_op.sv
ADD = 0
SUB = 1
RELU = 2
MUL = 3
D_RELU = 4


def float_to_fp32(f):
    """Convert Python float to IEEE 754 32-bit representation."""
    return struct.unpack('>I', struct.pack('>f', f))[0]


def fp32_to_float(bits):
    """Convert IEEE 754 32-bit representation to Python float."""
    return struct.unpack('>f', struct.pack('>I', bits))[0]


def fp32_approx_equal(a, b, rel_tol=1e-5, abs_tol=1e-6):
    """Check if two FP32 values are approximately equal."""
    fa = fp32_to_float(a)
    fb = fp32_to_float(b)
    if fa == fb:
        return True
    return abs(fa - fb) <= max(rel_tol * max(abs(fa), abs(fb)), abs_tol)


def bits_is_nan(bits):
    return ((bits & 0x7F800000) == 0x7F800000) and ((bits & 0x007FFFFF) != 0)


def bits_is_inf(bits):
    return ((bits & 0x7F800000) == 0x7F800000) and ((bits & 0x007FFFFF) == 0)


def bits_is_zero(bits):
    return (bits & 0x7FFFFFFF) == 0


@cocotb.test()
async def test_vpu_add_basic(dut):
    """Test VPU ADD operation."""
    test_cases = [(1.0, 2.0, 3.0), (0.5, 0.5, 1.0), (-1.0, 1.0, 0.0), (10.0, -5.0, 5.0)]
    dut.opcode.value = ADD
    dut.start.value = 1
    for a, b, expected in test_cases:
        dut.operand0.value = float_to_fp32(a)
        dut.operand1.value = float_to_fp32(b)
        await Timer(10, unit="ns")
        result = fp32_to_float(int(dut.result_out.value))
        assert abs(result - expected) < 0.001, f"ADD {a}+{b}={result}, expected {expected}"
    dut._log.info("PASS: VPU ADD test")


@cocotb.test()
async def test_vpu_sub_basic(dut):
    """Test VPU SUB operation."""
    test_cases = [(3.0, 1.0, 2.0), (1.0, 3.0, -2.0), (5.0, 5.0, 0.0)]
    dut.opcode.value = SUB
    dut.start.value = 1
    for a, b, expected in test_cases:
        dut.operand0.value = float_to_fp32(a)
        dut.operand1.value = float_to_fp32(b)
        await Timer(10, unit="ns")
        result = fp32_to_float(int(dut.result_out.value))
        assert abs(result - expected) < 0.001, f"SUB {a}-{b}={result}, expected {expected}"
    dut._log.info("PASS: VPU SUB test")


@cocotb.test()
async def test_vpu_relu(dut):
    """Test VPU RELU operation."""
    dut.opcode.value = RELU
    dut.start.value = 1
    # Positive values pass through
    for val in [1.0, 2.5, 100.0, 0.001]:
        dut.operand0.value = float_to_fp32(val)
        await Timer(10, unit="ns")
        result = fp32_to_float(int(dut.result_out.value))
        assert abs(result - val) < 0.001, f"RELU({val})={result}, expected {val}"
    # Negative values become 0
    for val in [-1.0, -2.5, -100.0]:
        dut.operand0.value = float_to_fp32(val)
        await Timer(10, unit="ns")
        result = fp32_to_float(int(dut.result_out.value))
        assert result == 0.0, f"RELU({val})={result}, expected 0.0"
    dut._log.info("PASS: VPU RELU test")


@cocotb.test()
async def test_vpu_mul_basic(dut):
    """Test VPU MUL operation."""
    test_cases = [(2.0, 3.0, 6.0), (0.5, 4.0, 2.0), (-2.0, 3.0, -6.0), (-2.0, -3.0, 6.0)]
    dut.opcode.value = MUL
    dut.start.value = 1
    for a, b, expected in test_cases:
        dut.operand0.value = float_to_fp32(a)
        dut.operand1.value = float_to_fp32(b)
        await Timer(10, unit="ns")
        result = fp32_to_float(int(dut.result_out.value))
        assert abs(result - expected) < 0.01, f"MUL {a}*{b}={result}, expected {expected}"
    dut._log.info("PASS: VPU MUL test")


@cocotb.test()
async def test_vpu_relu_derivative(dut):
    """Test VPU RELU_DERIVATIVE operation (opcode 4 per docs/system.md)."""
    dut.opcode.value = D_RELU
    dut.start.value = 1
    # For positive inputs, derivative = 1.0
    for val in [1.0, 2.5, 100.0, 0.001]:
        dut.operand0.value = float_to_fp32(val)
        await Timer(10, unit="ns")
        result = fp32_to_float(int(dut.result_out.value))
        assert abs(result - 1.0) < 0.001, f"RELU_DERIV({val})={result}, expected 1.0"
    # For negative inputs, derivative = 0.0
    for val in [-1.0, -2.5, -100.0]:
        dut.operand0.value = float_to_fp32(val)
        await Timer(10, unit="ns")
        result = fp32_to_float(int(dut.result_out.value))
        assert result == 0.0, f"RELU_DERIV({val})={result}, expected 0.0"
    # Edge case: zero
    dut.operand0.value = float_to_fp32(0.0)
    await Timer(10, unit="ns")
    dut._log.info("PASS: VPU RELU_DERIVATIVE test")


@cocotb.test()
async def test_vpu_randomized(dut):
    """Randomized test for VPU operations (all opcodes per docs/system.md)."""
    random.seed(77777)
    dut.start.value = 1
    for _ in range(50):
        a = random.uniform(-10.0, 10.0)
        b = random.uniform(-10.0, 10.0)
        op = random.choice([ADD, SUB, RELU, MUL, D_RELU])
        dut.operand0.value = float_to_fp32(a)
        dut.operand1.value = float_to_fp32(b)
        dut.opcode.value = op
        await Timer(10, unit="ns")
        result = fp32_to_float(int(dut.result_out.value))
        if op == ADD:
            expected = a + b
        elif op == SUB:
            expected = a - b
        elif op == RELU:
            expected = max(0.0, a)
        elif op == MUL:
            expected = a * b
        elif op == D_RELU:
            expected = 1.0 if a > 0 else 0.0
        assert abs(result - expected) < 0.1, f"Op {op}: got {result}, expected {expected}"
    dut._log.info("PASS: VPU randomized test")


@cocotb.test()
async def test_vpu_stress_fp32_edges(dut):
    """Stress VPU ops with FP32 edge cases (max/min/overflow/underflow/inf/nan)."""
    # FP32 edge constants
    MAX_FINITE = 0x7F7FFFFF
    MIN_NORMAL = 0x00800000
    MIN_SUB = 0x00000001
    POS_ZERO = 0x00000000
    NEG_ZERO = 0x80000000
    POS_INF = 0x7F800000
    NEG_INF = 0xFF800000
    QNAN = 0x7FC00000

    dut.start.value = 1

    # ADD overflow: max + max -> +inf
    dut.opcode.value = ADD
    dut.operand0.value = MAX_FINITE
    dut.operand1.value = MAX_FINITE
    await Timer(10, unit="ns")
    res_bits = int(dut.result_out.value)
    assert bits_is_inf(res_bits), f"ADD overflow expected +inf, got 0x{res_bits:08x}"

    # # ADD subnormal + subnormal -> small subnormal (expect 0x00000002)
    dut.operand0.value = MIN_SUB
    dut.operand1.value = MIN_SUB
    await Timer(10, unit="ns")
    res_bits = int(dut.result_out.value)
    assert res_bits == 0x00000002, f"ADD subnormals expected 0x00000002, got 0x{res_bits:08x}"

    # ADD inf + (-inf) -> NaN
    dut.operand0.value = POS_INF
    dut.operand1.value = NEG_INF
    await Timer(10, unit="ns")
    res_bits = int(dut.result_out.value)
    assert bits_is_nan(res_bits), f"ADD inf + -inf expected NaN, got 0x{res_bits:08x}"

    # SUB: max - (-max) -> +inf
    dut.opcode.value = SUB
    dut.operand0.value = MAX_FINITE
    dut.operand1.value = 0xFF7FFFFF  # -max
    await Timer(10, unit="ns")
    res_bits = int(dut.result_out.value)
    assert bits_is_inf(res_bits), f"SUB overflow expected +inf, got 0x{res_bits:08x}"

    # SUB: max - max -> +0 (sign can vary)
    dut.operand0.value = MAX_FINITE
    dut.operand1.value = MAX_FINITE
    await Timer(10, unit="ns")
    res_bits = int(dut.result_out.value)
    assert bits_is_zero(res_bits), f"SUB equal expected 0, got 0x{res_bits:08x}"

    # MUL overflow: max * 2 -> +inf
    dut.opcode.value = MUL
    dut.operand0.value = MAX_FINITE
    dut.operand1.value = float_to_fp32(2.0)
    await Timer(10, unit="ns")
    res_bits = int(dut.result_out.value)
    assert bits_is_inf(res_bits), f"MUL overflow expected +inf, got 0x{res_bits:08x}"

    # # MUL underflow: min_normal * min_normal -> 0
    dut.operand0.value = MIN_NORMAL
    dut.operand1.value = MIN_NORMAL
    await Timer(10, unit="ns")
    res_bits = int(dut.result_out.value)
    assert bits_is_zero(res_bits), f"MUL underflow expected 0, got 0x{res_bits:08x}"

    # MUL: inf * 0 -> NaN
    dut.operand0.value = POS_INF
    dut.operand1.value = POS_ZERO
    await Timer(10, unit="ns")
    res_bits = int(dut.result_out.value)
    assert bits_is_nan(res_bits), f"MUL inf*0 expected NaN, got 0x{res_bits:08x}"

    # MUL: inf * -1 -> -inf
    dut.operand0.value = POS_INF
    dut.operand1.value = float_to_fp32(-1.0)
    await Timer(10, unit="ns")
    res_bits = int(dut.result_out.value)
    assert bits_is_inf(res_bits) and (res_bits & 0x80000000), f"MUL inf*-1 expected -inf, got 0x{res_bits:08x}"

    # ADD: NaN propagation
    dut.opcode.value = ADD
    dut.operand0.value = QNAN
    dut.operand1.value = float_to_fp32(1.0)
    await Timer(10, unit="ns")
    res_bits = int(dut.result_out.value)
    assert bits_is_nan(res_bits), f"ADD NaN expected NaN, got 0x{res_bits:08x}"

    # RELU with negative max -> 0
    dut.opcode.value = RELU
    dut.operand0.value = 0xFF7FFFFF  # -max
    await Timer(10, unit="ns")
    res_bits = int(dut.result_out.value)
    assert bits_is_zero(res_bits), f"RELU(-max) expected 0, got 0x{res_bits:08x}"

    # RELU with +0 / -0 stays zero
    for zero in (POS_ZERO, NEG_ZERO):
        dut.operand0.value = zero
        await Timer(10, unit="ns")
        res_bits = int(dut.result_out.value)
        assert bits_is_zero(res_bits), f"RELU(zero) expected 0, got 0x{res_bits:08x}"

    dut._log.info("PASS: VPU FP32 edge-case stress test")
