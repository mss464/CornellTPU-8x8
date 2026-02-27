"""Functional tests for vpu_simd.sv - SIMD VPU with register file."""

import cocotb
from cocotb.triggers import RisingEdge
from cocotb.clock import Clock
import struct

def float_to_fp32(f):
    return struct.unpack('>I', struct.pack('>f', f))[0]

def fp32_to_float(bits):
    return struct.unpack('>f', struct.pack('>I', bits))[0]


@cocotb.test()
async def test_vpu_simd_reset(dut):
    """Test that reset brings VPU to IDLE state."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.vpu_type.value = 0
    dut.addr_a.value = 0
    dut.addr_out.value = 0
    dut.vreg_dst.value = 0
    dut.vreg_a.value = 0
    dut.vreg_b.value = 0
    dut.vpu_opcode.value = 0
    dut.scalar_b.value = 0
    dut.bram_dout.value = 0

    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Verify idle state
    assert int(dut.done.value) == 0, "Done should be 0 after reset"
    assert int(dut.bram_en.value) == 0, "BRAM enable should be 0 in IDLE"

    dut._log.info("PASS: VPU SIMD reset to IDLE")


@cocotb.test()
async def test_vcompute_simple(dut):
    """Test VCOMPUTE operation (without actual BRAM)."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.vpu_type.value = 0
    dut.addr_a.value = 0
    dut.addr_out.value = 0
    dut.vreg_dst.value = 0
    dut.vreg_a.value = 0
    dut.vreg_b.value = 0
    dut.vpu_opcode.value = 0
    dut.scalar_b.value = 0
    dut.bram_dout.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Setup VCOMPUTE: V2 = V0 + V1 (registers start at zero, so result should be zero)
    dut.vpu_type.value = 3  # VCOMPUTE
    dut.vpu_opcode.value = 0  # VADD
    dut.vreg_dst.value = 2
    dut.vreg_a.value = 0
    dut.vreg_b.value = 1
    dut.scalar_b.value = 0
    dut.start.value = 1

    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Wait for done signal
    cycle_count = 0
    while cycle_count < 20:
        await RisingEdge(dut.clk)
        if int(dut.done.value) == 1:
            break
        cycle_count += 1

    assert cycle_count < 20, "VCOMPUTE timeout"
    assert cycle_count <= 3, f"VCOMPUTE should complete in 1-3 cycles, took {cycle_count}"

    dut._log.info(f"PASS: VCOMPUTE completed in {cycle_count} cycles")


@cocotb.test()
async def test_vload_sequential(dut):
    """Test VLOAD reading 8 sequential elements from BRAM."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Simple BRAM model
    bram = {}
    for i in range(8):
        bram[100 + i] = float_to_fp32(float(i + 10))

    # Reset
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.vpu_type.value = 0
    dut.addr_a.value = 0
    dut.addr_out.value = 0
    dut.vreg_dst.value = 0
    dut.vreg_a.value = 0
    dut.vreg_b.value = 0
    dut.vpu_opcode.value = 0
    dut.scalar_b.value = 0
    dut.bram_dout.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Trigger VLOAD: V0 = BRAM[100:107]
    dut.vpu_type.value = 1  # VLOAD
    dut.addr_a.value = 100
    dut.vreg_dst.value = 0
    dut.start.value = 1

    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Simulate BRAM reads over multiple cycles
    cycle_count = 0
    read_count = 0
    last_addr = None
    while cycle_count < 100:
        await RisingEdge(dut.clk)

        # Check if BRAM read is active
        if int(dut.bram_en.value) == 1 and int(dut.bram_we.value) == 0:
            addr = int(dut.bram_addr.value)
            if addr in bram:
                dut.bram_dout.value = bram[addr]
                if addr != last_addr:
                    read_count += 1
                    last_addr = addr

        if int(dut.done.value) == 1:
            break
        cycle_count += 1

    assert cycle_count < 100, "VLOAD timeout"
    assert read_count == 8, f"Expected 8 BRAM reads, got {read_count}"

    dut._log.info(f"PASS: VLOAD completed in {cycle_count} cycles with {read_count} reads")


@cocotb.test()
async def test_vstore_sequential(dut):
    """Test VSTORE writing 8 sequential elements to BRAM."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # BRAM model to capture writes
    bram_writes = {}

    # Reset
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.vpu_type.value = 0
    dut.addr_a.value = 0
    dut.addr_out.value = 0
    dut.vreg_dst.value = 0
    dut.vreg_a.value = 0
    dut.vreg_b.value = 0
    dut.vpu_opcode.value = 0
    dut.scalar_b.value = 0
    dut.bram_dout.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Trigger VSTORE: BRAM[200:207] = V1 (register V1 starts at zero)
    dut.vpu_type.value = 2  # VSTORE
    dut.addr_out.value = 200
    dut.vreg_a.value = 1
    dut.start.value = 1

    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Capture BRAM writes
    cycle_count = 0
    write_count = 0
    while cycle_count < 100:
        await RisingEdge(dut.clk)

        # Check if BRAM write is active
        if int(dut.bram_en.value) == 1 and int(dut.bram_we.value) == 1:
            addr = int(dut.bram_addr.value)
            data = int(dut.bram_din.value)
            bram_writes[addr] = data
            write_count += 1

        if int(dut.done.value) == 1:
            break
        cycle_count += 1

    assert cycle_count < 100, "VSTORE timeout"
    assert write_count == 8, f"Expected 8 BRAM writes, got {write_count}"

    # Verify writes went to correct addresses
    for i in range(8):
        assert (200 + i) in bram_writes, f"Missing write to address {200 + i}"

    dut._log.info(f"PASS: VSTORE completed in {cycle_count} cycles with {write_count} writes")


@cocotb.test()
async def test_vcompute_scalar_broadcast(dut):
    """Test scalar broadcast mode (V2 = V0 * V1[0])."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.vpu_type.value = 0
    dut.addr_a.value = 0
    dut.addr_out.value = 0
    dut.vreg_dst.value = 0
    dut.vreg_a.value = 0
    dut.vreg_b.value = 0
    dut.vpu_opcode.value = 0
    dut.scalar_b.value = 0
    dut.bram_dout.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Setup VMUL with scalar broadcast: V2 = V0 * V1[0]
    dut.vpu_type.value = 3  # VCOMPUTE
    dut.vpu_opcode.value = 2  # VMUL
    dut.vreg_dst.value = 2
    dut.vreg_a.value = 0
    dut.vreg_b.value = 1
    dut.scalar_b.value = 1  # Enable scalar broadcast
    dut.start.value = 1

    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Wait for done
    cycle_count = 0
    while cycle_count < 20:
        await RisingEdge(dut.clk)
        if int(dut.done.value) == 1:
            break
        cycle_count += 1

    assert cycle_count < 20, "VMUL scalar broadcast timeout"

    dut._log.info(f"PASS: Scalar broadcast VMUL completed in {cycle_count} cycles")


@cocotb.test()
async def test_invalid_vpu_type(dut):
    """Test that invalid VPU_TYPE completes without hanging."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.vpu_type.value = 0
    dut.addr_a.value = 0
    dut.addr_out.value = 0
    dut.vreg_dst.value = 0
    dut.vreg_a.value = 0
    dut.vreg_b.value = 0
    dut.vpu_opcode.value = 0
    dut.scalar_b.value = 0
    dut.bram_dout.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Trigger with invalid VPU_TYPE
    dut.vpu_type.value = 7  # Invalid (only 0-3 are valid)
    dut.start.value = 1

    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Should go to DONE_STATE immediately
    cycle_count = 0
    while cycle_count < 10:
        await RisingEdge(dut.clk)
        if int(dut.done.value) == 1:
            break
        cycle_count += 1

    assert cycle_count < 10, "Invalid VPU_TYPE should complete quickly"

    dut._log.info(f"PASS: Invalid VPU_TYPE handled gracefully in {cycle_count} cycles")


@cocotb.test()
async def test_vpu_simd_data_correctness(dut):
    """Verify data correctness: VLOAD V0, VLOAD V1, VADD V2=V0+V1, VSTORE V2.

    This test validates that vpu_simd.sv correctly pipelines data through the
    load→compute→store path, not just that control signals fire.
    """
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.vpu_type.value = 0
    dut.addr_a.value = 0
    dut.addr_out.value = 0
    dut.vreg_dst.value = 0
    dut.vreg_a.value = 0
    dut.vreg_b.value = 0
    dut.vpu_opcode.value = 0
    dut.scalar_b.value = 0
    dut.bram_dout.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Build BRAM model with known float values
    bram = {}
    v0_vals = [float(i + 1) for i in range(8)]    # [1.0, 2.0, ..., 8.0]
    v1_vals = [float(i * 2 + 1) for i in range(8)]  # [1.0, 3.0, 5.0, ..., 15.0]
    for i in range(8):
        bram[50 + i] = float_to_fp32(v0_vals[i])
    for i in range(8):
        bram[60 + i] = float_to_fp32(v1_vals[i])
    expected = [v0_vals[i] + v1_vals[i] for i in range(8)]

    async def run_op(vpu_type, addr_a=0, addr_out=0, vreg_dst=0,
                     vreg_a=0, vreg_b=0, vpu_opcode=0):
        """Run one VPU operation, serving BRAM reads and capturing writes."""
        dut.vpu_type.value = vpu_type
        dut.addr_a.value = addr_a
        dut.addr_out.value = addr_out
        dut.vreg_dst.value = vreg_dst
        dut.vreg_a.value = vreg_a
        dut.vreg_b.value = vreg_b
        dut.vpu_opcode.value = vpu_opcode
        dut.scalar_b.value = 0
        dut.start.value = 1
        await RisingEdge(dut.clk)
        dut.start.value = 0

        for _ in range(200):
            await RisingEdge(dut.clk)
            if int(dut.bram_en.value) == 1 and int(dut.bram_we.value) == 0:
                # Serve BRAM read: drive dout from model
                dut.bram_dout.value = bram.get(int(dut.bram_addr.value), 0)
            elif int(dut.bram_en.value) == 1 and int(dut.bram_we.value) == 1:
                # Capture BRAM write into model
                bram[int(dut.bram_addr.value)] = int(dut.bram_din.value)
            if int(dut.done.value) == 1:
                return
        raise AssertionError(f"VPU op (vpu_type={vpu_type}) timed out")

    # Step 1: VLOAD V0 from BRAM[50:57]
    await run_op(vpu_type=1, addr_a=50, vreg_dst=0)

    # Step 2: VLOAD V1 from BRAM[60:67]
    await run_op(vpu_type=1, addr_a=60, vreg_dst=1)

    # Step 3: VCOMPUTE V2 = V0 + V1 (vadd, opcode=0)
    await run_op(vpu_type=3, vreg_a=0, vreg_b=1, vreg_dst=2, vpu_opcode=0)

    # Step 4: VSTORE V2 to BRAM[70:77]
    await run_op(vpu_type=2, addr_out=70, vreg_a=2)

    # Verify: BRAM[70:77] == expected element-wise sums (FP32 bit-exact)
    for i in range(8):
        addr = 70 + i
        assert addr in bram, f"Missing BRAM write at address {addr}"
        got = fp32_to_float(bram[addr])
        exp = expected[i]
        assert abs(got - exp) < 1e-4, \
            f"Data mismatch at V2[{i}]: expected {exp}, got {got}"

    dut._log.info("PASS: test_vpu_simd_data_correctness — VLOAD→VADD→VSTORE data verified")


# ---------------------------------------------------------------------------
# P2.06 — SCALAR VPU tests
# ---------------------------------------------------------------------------

def _reset_signals(dut):
    """Drive all inputs to safe defaults before asserting rst_n."""
    dut.rst_n.value = 0
    dut.start.value = 0
    for sig in [dut.vpu_type, dut.addr_a, dut.addr_b, dut.addr_out,
                dut.vreg_dst, dut.vreg_a, dut.vreg_b, dut.vpu_opcode,
                dut.scalar_b, dut.bram_dout]:
        sig.value = 0


async def _run_scalar_op(dut, vpu_type, vpu_opcode, addr_a, addr_b, addr_out,
                         bram_init, timeout=30):
    """
    Run one SCALAR VPU operation and return (written_addr, written_bits).

    bram_init: dict {addr: uint32_bits}
    Returns: (addr_written, data_written_as_int) or (None, None) on timeout.
    """
    dut.vpu_type.value  = vpu_type
    dut.vpu_opcode.value = vpu_opcode
    dut.addr_a.value    = addr_a
    dut.addr_b.value    = addr_b
    dut.addr_out.value  = addr_out
    dut.start.value     = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    written_addr = [None]
    written_data = [None]

    for _ in range(timeout):
        await RisingEdge(dut.clk)

        # Serve BRAM reads
        if int(dut.bram_en.value) and not int(dut.bram_we.value):
            addr = int(dut.bram_addr.value)
            dut.bram_dout.value = bram_init.get(addr, 0)

        # Capture BRAM writes
        if int(dut.bram_en.value) and int(dut.bram_we.value):
            written_addr[0] = int(dut.bram_addr.value)
            written_data[0] = int(dut.bram_din.value)

        if int(dut.done.value):
            break

    return written_addr[0], written_data[0]


@cocotb.test()
async def test_scalar_add(dut):
    """SCALAR ADD: bram[2] = bram[0] + bram[1]  (3.0 + 4.0 = 7.0)"""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())
    _reset_signals(dut)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    bram = {0: float_to_fp32(3.0), 1: float_to_fp32(4.0)}

    wr_addr, wr_data = await _run_scalar_op(
        dut,
        vpu_type=0,   # SCALAR
        vpu_opcode=0, # ADD
        addr_a=0, addr_b=1, addr_out=2,
        bram_init=bram,
    )

    assert wr_addr == 2, f"Expected write to addr 2, got {wr_addr}"
    result = fp32_to_float(wr_data)
    assert abs(result - 7.0) < 1e-5, f"Expected 3.0+4.0=7.0, got {result}"
    dut._log.info(f"PASS: test_scalar_add — result={result}")


@cocotb.test()
async def test_scalar_relu(dut):
    """SCALAR RELU: bram[1] = relu(bram[0])  where bram[0] is -2.5 → 0.0"""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())
    _reset_signals(dut)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    bram = {0: float_to_fp32(-2.5)}

    wr_addr, wr_data = await _run_scalar_op(
        dut,
        vpu_type=0,   # SCALAR
        vpu_opcode=2, # RELU
        addr_a=0, addr_b=0, addr_out=1,
        bram_init=bram,
    )

    assert wr_addr == 1, f"Expected write to addr 1, got {wr_addr}"
    result = fp32_to_float(wr_data)
    assert result == 0.0, f"Expected relu(-2.5)=0.0, got {result}"
    dut._log.info(f"PASS: test_scalar_relu — result={result}")


@cocotb.test()
async def test_scalar_mul(dut):
    """SCALAR MUL: bram[2] = bram[0] * bram[1]  (2.5 * 4.0 = 10.0)"""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())
    _reset_signals(dut)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    bram = {0: float_to_fp32(2.5), 1: float_to_fp32(4.0)}

    wr_addr, wr_data = await _run_scalar_op(
        dut,
        vpu_type=0,   # SCALAR
        vpu_opcode=3, # MUL
        addr_a=0, addr_b=1, addr_out=2,
        bram_init=bram,
    )

    assert wr_addr == 2, f"Expected write to addr 2, got {wr_addr}"
    result = fp32_to_float(wr_data)
    assert abs(result - 10.0) < 1e-4, f"Expected 2.5*4.0=10.0, got {result}"
    dut._log.info(f"PASS: test_scalar_mul — result={result}")
