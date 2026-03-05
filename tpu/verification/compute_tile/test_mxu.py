import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import numpy as np
import struct

N = 4
DATA_WIDTH = 32
BANKING_FACTOR = 8
COMP_DATA_WIDTH = 256

BASE_ADDR_W = 0x000
BASE_ADDR_X = 0x100
BASE_ADDR_OUT = 0x200
TIMEOUT_CYCLES = 2000


def float_to_fp32_bits(val: float) -> int:
    """Convert Python float to 32-bit IEEE-754 single-precision bit pattern."""
    return struct.unpack(">I", struct.pack(">f", float(val)))[0]


def fp32_bits_to_float(bits: int) -> float:
    """Convert 32-bit IEEE-754 bit pattern to Python float."""
    bits = bits & 0xFFFFFFFF
    return struct.unpack(">f", struct.pack(">I", bits))[0]


def pack_row(row_vals):
    """Pack a row of N elements into a COMP_DATA_WIDTH integer."""
    res = 0
    for i, v in enumerate(row_vals):
        res |= (float_to_fp32_bits(v) & 0xFFFFFFFF) << (i * DATA_WIDTH)
    return res


def unpack_row(val):
    """Unpack a COMP_DATA_WIDTH integer into N elements."""
    return [(val >> (i * DATA_WIDTH)) & 0xFFFFFFFF for i in range(N)]


async def reset_dut(dut):
    """Assert active-low reset and return to a clean idle state."""
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.base_addr_w.value = BASE_ADDR_W
    dut.base_addr_x.value = BASE_ADDR_X
    dut.base_addr_out.value = BASE_ADDR_OUT
    dut.mem_resp_data.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def memory_driver(dut, mem):
    """Memory model - handles COMP_DATA_WIDTH (256-bit) width."""
    last_addr = 0
    while True:
        await RisingEdge(dut.clk)

        # Sample interface signals
        try:
            rd_en = int(dut.mem_read_en.value)
            addr = int(dut.mem_req_addr.value)
            wr_en = int(dut.mem_write_en.value)
            wr_data = int(dut.mem_req_data.value)
        except ValueError:
            rd_en = 0
            addr = 0
            wr_en = 0
            wr_data = 0

        if rd_en:
            last_addr = addr  # Latch address when read request is made
        if wr_en:
            mem[addr] = wr_data  # Store the full 256-bit word

        # Always output data for the latched address
        dut.mem_resp_data.value = mem.get(last_addr, 0)


def load_matrices(mem, w_base, x_base, w_mat, x_mat):
    """Load matrices into memory row-by-row as packed 256-bit words."""
    # w_mat and x_mat are NxN numpy arrays
    for i in range(N):
        # Load row i of W
        mem[w_base + i] = pack_row(w_mat[i, :])
        # Load row i of X
        mem[x_base + i] = pack_row(x_mat[i, :])


async def run_matmul(dut, mem, w_mat, x_mat):
    """Run one matmul through the wrapper and return output matrix."""
    load_matrices(mem, BASE_ADDR_W, BASE_ADDR_X, w_mat, x_mat)

    dut.base_addr_w.value = BASE_ADDR_W
    dut.base_addr_x.value = BASE_ADDR_X
    dut.base_addr_out.value = BASE_ADDR_OUT

    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        if int(dut.done.value):
            break
    else:
        raise cocotb.result.TestFailure("Timeout waiting for done")

    await RisingEdge(dut.clk)

    # Read output from memory (row-by-row)
    out = np.zeros((N, N), dtype=float)
    dut._log.info(f"Memory Output reading from base addr: {BASE_ADDR_OUT}")
    for i in range(N):
        packed_val = mem.get(BASE_ADDR_OUT + i, 0)
        unpacked = unpack_row(packed_val)
        dut._log.info(f"Row {i} Packed: {hex(packed_val)} Unpacked: {[fp32_bits_to_float(v) for v in unpacked]}")
        for j in range(N):
            out[i, j] = fp32_bits_to_float(unpacked[j])
            
    # Also verify the internal OUT_DEBUG for good measure (Icarus specific)
    internal_out = np.zeros((N, N), dtype=float)
    for i in range(N):
        for j in range(N):
            idx = i * N + j
            try:
                raw = int(dut.OUT_DEBUG[idx].out_elem.value)
                raw_float = fp32_bits_to_float(raw)
                internal_out[i, j] = raw_float
                if abs(raw_float - out[i, j]) > 1e-5:
                     dut._log.warning(f"Internal state mismatch at [{i},{j}]: internal={raw_float}, mem={out[i,j]}")
            except AttributeError:
                pass # Verilator or non-debug build
                
    dut._log.info(f"Internal OUT_MATRIX:\n{internal_out}")
    dut._log.info(f"Expected Exp:\n{x_mat @ w_mat.T}")

                
    return out


def assert_matrix_close(actual, expected, rtol=1e-3, atol=1e-3):
    """Compare matrices with NaN/Inf handling."""
    for i in range(N):
        for j in range(N):
            a = actual[i, j]
            e = expected[i, j]
            if np.isnan(e):
                assert np.isnan(a), f"[{i},{j}] expected NaN, got {a}"
            elif np.isinf(e):
                assert np.isinf(a) and np.sign(a) == np.sign(e), f"[{i},{j}] expected {e}, got {a}"
            else:
                assert abs(a - e) <= max(rtol * max(abs(a), abs(e)), atol), f"[{i},{j}] {a} != {e}"


@cocotb.test()
async def test_sequential_matmul_no_reset(dut):
    """Two matmuls back-to-back without reset should not leak state."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    mem = {}
    cocotb.start_soon(memory_driver(dut, mem))

    await reset_dut(dut)

    rng = np.random.default_rng(42)

    w1 = rng.uniform(-2.0, 2.0, size=(N, N)).astype(float)
    x1 = rng.uniform(-2.0, 2.0, size=(N, N)).astype(float)
    out1 = await run_matmul(dut, mem, w1, x1)
    exp1 = x1 @ w1.T
    assert np.allclose(out1, exp1, rtol=1e-3, atol=1e-3), f"Run 1 mismatch:\nGot:\n{out1}\nExp:\n{exp1}"

    w2 = rng.uniform(-2.0, 2.0, size=(N, N)).astype(float)
    x2 = rng.uniform(-2.0, 2.0, size=(N, N)).astype(float)
    out2 = await run_matmul(dut, mem, w2, x2)
    exp2 = x2 @ w2.T
    assert np.allclose(out2, exp2, rtol=1e-3, atol=1e-3), f"Run 2 mismatch:\nGot:\n{out2}\nExp:\n{exp2}"


@cocotb.test()
async def test_alternating_weight_patterns(dut):
    """Zero weights after a nonzero run should produce zero output."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    mem = {}
    cocotb.start_soon(memory_driver(dut, mem))

    await reset_dut(dut)

    rng = np.random.default_rng(7)
    w1 = rng.uniform(-1.5, 1.5, size=(N, N)).astype(float)
    x1 = rng.uniform(-1.5, 1.5, size=(N, N)).astype(float)
    out1 = await run_matmul(dut, mem, w1, x1)
    exp1 = x1 @ w1.T
    assert np.allclose(out1, exp1, rtol=1e-3, atol=1e-3), "Baseline mismatch"

    w2 = np.zeros((N, N), dtype=float)
    x2 = rng.uniform(-1.5, 1.5, size=(N, N)).astype(float)
    out2 = await run_matmul(dut, mem, w2, x2)
    exp2 = np.zeros((N, N), dtype=float)
    assert np.allclose(out2, exp2, rtol=1e-5, atol=1e-5), "Zero-weight run mismatch"


@cocotb.test()
async def test_multiple_sequential_random(dut):
    """Stress test multiple sequential matmuls without reset."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    mem = {}
    cocotb.start_soon(memory_driver(dut, mem))

    await reset_dut(dut)

    rng = np.random.default_rng(1234)
    for _ in range(10):
        w = rng.uniform(-2.0, 2.0, size=(N, N)).astype(float)
        x = rng.uniform(-2.0, 2.0, size=(N, N)).astype(float)
        out = await run_matmul(dut, mem, w, x)
        exp = x @ w.T
        assert np.allclose(out, exp, rtol=1e-2, atol=1e-2), "Sequential run mismatch"


@cocotb.test()
async def test_fp32_extremes(dut):
    """Edge-case FP32 values: max/min/overflow/underflow."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    mem = {}
    cocotb.start_soon(memory_driver(dut, mem))
    await reset_dut(dut)

    max_f = np.float32(np.finfo(np.float32).max)
    min_n = np.float32(np.finfo(np.float32).tiny)
    # Craft matrices that will overflow and underflow
    w = np.array([
        [max_f, 0, 0, 0],
        [0, min_n, 0, 0],
        [0, 0, max_f, 0],
        [0, 0, 0, min_n],
    ], dtype=np.float32)
    x = np.array([
        [max_f, 0, 0, 0],
        [0, min_n, 0, 0],
        [0, 0, max_f, 0],
        [0, 0, 0, min_n],
    ], dtype=np.float32)

    out = await run_matmul(dut, mem, w.astype(float), x.astype(float))
    exp = (x @ w.T).astype(np.float32)
    assert_matrix_close(out, exp, rtol=1e-2, atol=1e-2)


@cocotb.test()
async def test_back_to_back_start(dut):
    """Back-to-back start pulses with no idle cycles."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    mem = {}
    cocotb.start_soon(memory_driver(dut, mem))
    await reset_dut(dut)

    rng = np.random.default_rng(99)
    w1 = rng.uniform(-1.0, 1.0, size=(N, N)).astype(float)
    x1 = rng.uniform(-1.0, 1.0, size=(N, N)).astype(float)
    out1 = await run_matmul(dut, mem, w1, x1)
    exp1 = x1 @ w1.T
    assert np.allclose(out1, exp1, rtol=1e-3, atol=1e-3), "Run 1 mismatch"

    # Immediately start second run on next cycle after done
    w2 = rng.uniform(-1.0, 1.0, size=(N, N)).astype(float)
    x2 = rng.uniform(-1.0, 1.0, size=(N, N)).astype(float)
    load_matrices(mem, BASE_ADDR_W, BASE_ADDR_X, w2, x2)
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        if int(dut.done.value):
            break
    else:
        raise cocotb.result.TestFailure("Timeout waiting for done (run2)")

    await RisingEdge(dut.clk)
    # Read output from memory
    out2 = np.zeros((N, N), dtype=float)
    for i in range(N):
        packed_val = mem.get(BASE_ADDR_OUT + i, 0)
        unpacked = unpack_row(packed_val)
        for j in range(N):
            out2[i, j] = fp32_bits_to_float(unpacked[j])
            
    exp2 = x2 @ w2.T
    assert np.allclose(out2, exp2, rtol=1e-3, atol=1e-3), "Run 2 mismatch"


@cocotb.test()
async def test_row_column_boundary(dut):
    """Single-element activations to validate boundary propagation."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    mem = {}
    cocotb.start_soon(memory_driver(dut, mem))
    await reset_dut(dut)

    w = np.eye(N, dtype=float)
    x = np.zeros((N, N), dtype=float)
    x[0, 0] = 1.0
    x[N - 1, N - 1] = -2.0
    out = await run_matmul(dut, mem, w, x)
    exp = x @ w.T
    assert np.allclose(out, exp, rtol=1e-5, atol=1e-5), "Boundary propagation mismatch"


@cocotb.test()
async def test_base_addr_aliasing_writeback(dut):
    """Alias OUT over W and verify writeback occurs (diagnostic)."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    mem = {}
    cocotb.start_soon(memory_driver(dut, mem))
    await reset_dut(dut)

    rng = np.random.default_rng(202)
    w = rng.uniform(-1.0, 1.0, size=(N, N)).astype(float)
    x = rng.uniform(-1.0, 1.0, size=(N, N)).astype(float)
    load_matrices(mem, BASE_ADDR_W, BASE_ADDR_X, w, x)

    # Alias OUT with W
    dut.base_addr_w.value = BASE_ADDR_W
    dut.base_addr_x.value = BASE_ADDR_X
    dut.base_addr_out.value = BASE_ADDR_W

    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        if int(dut.done.value):
            break
    else:
        raise cocotb.result.TestFailure("Timeout waiting for done")

    # Verify that at least one weight location was overwritten by output
    exp = (x @ w.T).flatten()
    changed = 0
    for i in range(N):
        packed_val = mem.get(BASE_ADDR_W + i, 0)
        unpacked = unpack_row(packed_val)
        for j in range(N):
             if abs(fp32_bits_to_float(unpacked[j]) - exp[i*N + j]) < 1e-4:
                 changed += 1
                 
    assert changed > 0, "Expected writeback to overlap W region but saw no changes"
