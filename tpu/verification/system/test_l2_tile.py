"""
test_l2_tile.py — Verification for L2 tile and L1↔L2 data paths.

Tests the new memory hierarchy:
  Host → DevMem (mode 1) → L2 (mode 5) → L1 (mode 7) → [compute] → L1 → L2 (mode 8) → DevMem (mode 6) → Host (mode 2)
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import numpy as np
from test_tpu import TpuRtlDriver, float_to_int, int_to_float


def start_clocks(dut):
    cocotb.start_soon(Clock(dut.s00_axi_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.s00_axis_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.m00_axis_aclk, 10, units="ns").start())


# ---------------------------------------------------------------------------
# Test 1: DevMem → L2 → DevMem round-trip (modes 5 then 6)
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_dm_l2_roundtrip(dut):
    """Write to devmem, copy to L2, copy back to devmem at different offset, read and verify."""
    start_clocks(dut)
    driver = TpuRtlDriver(dut)
    await driver.reset()

    size = 32
    pattern = np.arange(1, size + 1, dtype=np.float32)

    # Write to devmem at offset 0
    await driver.write_bram(0, pattern)

    # Copy devmem[0..31] → L2[0..31] (mode 5)
    await driver.devmem_to_l2(devmem_addr=0, l2_addr=0, length=size)

    # Copy L2[0..31] → devmem[0x100..0x11F] (mode 6)
    await driver.l2_to_devmem(l2_addr=0, devmem_addr=0x100, length=size)

    # Read back from devmem[0x100]
    result = await driver.read_bram(0x100, size)

    for i in range(size):
        assert abs(result[i] - pattern[i]) < 1e-6, \
            f"DM→L2→DM mismatch at [{i}]: expected {pattern[i]}, got {result[i]}"

    dut._log.info("test_dm_l2_roundtrip PASSED")


# ---------------------------------------------------------------------------
# Test 2: DevMem → L2 → L1 → L2 → DevMem round-trip (modes 5, 7, 8, 6)
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_dm_l2_l1_l2_dm_roundtrip(dut):
    """Full hierarchy round-trip: host→devmem→L2→L1→L2→devmem→host."""
    start_clocks(dut)
    driver = TpuRtlDriver(dut)
    await driver.reset()

    size = 16
    pattern = np.array([float(i * 3 + 1) for i in range(size)], dtype=np.float32)

    # 1. Host → DevMem (mode 1)
    await driver.write_bram(0, pattern)

    # 2. DevMem[0] → L2[0x200] (mode 5)
    await driver.devmem_to_l2(devmem_addr=0, l2_addr=0x200, length=size)

    # 3. L2[0x200] → L1[0] (mode 7; L1 base=0)
    await driver.l2_to_l1(l2_addr=0x200, l1_base_addr=0, length=size)

    # 4. L1[0] → L2[0x400] (mode 8)
    await driver.l1_to_l2(l1_base_addr=0, l2_addr=0x400, length=size)

    # 5. L2[0x400] → DevMem[0x300] (mode 6)
    await driver.l2_to_devmem(l2_addr=0x400, devmem_addr=0x300, length=size)

    # 6. Host ← DevMem[0x300] (mode 2)
    result = await driver.read_bram(0x300, size)

    for i in range(size):
        assert abs(result[i] - pattern[i]) < 1e-6, \
            f"Full round-trip mismatch at [{i}]: expected {pattern[i]}, got {result[i]}"

    dut._log.info("test_dm_l2_l1_l2_dm_roundtrip PASSED")


# ---------------------------------------------------------------------------
# Test 3: L2→L1 transfer sizes (16, 64, 128)
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_l2_l1_sizes(dut):
    """Test L2→L1 copies of various sizes."""
    start_clocks(dut)
    driver = TpuRtlDriver(dut)
    await driver.reset()

    for size in [16, 64, 128]:
        pattern = np.arange(size, dtype=np.float32) * 0.5

        # Host → DevMem
        await driver.write_bram(0, pattern)
        # DevMem → L2
        await driver.devmem_to_l2(devmem_addr=0, l2_addr=0, length=size)
        # L2 → L1
        await driver.l2_to_l1(l2_addr=0, l1_base_addr=0, length=size)
        # L1 → L2 (at different addr)
        await driver.l1_to_l2(l1_base_addr=0, l2_addr=0x1000, length=size)
        # L2 → DevMem
        await driver.l2_to_devmem(l2_addr=0x1000, devmem_addr=0, length=size)
        # Read back
        result = await driver.read_bram(0, size)

        for i in range(size):
            assert abs(result[i] - pattern[i]) < 1e-6, \
                f"Size {size}, index {i}: expected {pattern[i]}, got {result[i]}"
        dut._log.info(f"  Size {size}: OK")

    dut._log.info("test_l2_l1_sizes PASSED")


# ---------------------------------------------------------------------------
# Test 4: Base address independence (L2 and L1 offsets)
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_l2_l1_base_addr_offset(dut):
    """Write to L2 at offset, transfer to L1 at offset, verify isolation."""
    start_clocks(dut)
    driver = TpuRtlDriver(dut)
    await driver.reset()

    size = 8
    pattern_a = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], dtype=np.float32)
    pattern_b = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0], dtype=np.float32)

    # Write pattern_a to devmem[0], pattern_b to devmem[0x100]
    await driver.write_bram(0, pattern_a)
    await driver.write_bram(0x100, pattern_b)

    # Copy both to L2 at different offsets
    await driver.devmem_to_l2(devmem_addr=0, l2_addr=0x000, length=size)
    await driver.devmem_to_l2(devmem_addr=0x100, l2_addr=0x100, length=size)

    # Copy L2[0x100] (pattern_b) to L1[0]
    await driver.l2_to_l1(l2_addr=0x100, l1_base_addr=0, length=size)

    # Writeback L1[0] → L2[0x200]
    await driver.l1_to_l2(l1_base_addr=0, l2_addr=0x200, length=size)

    # L2[0x200] → DevMem[0x200]
    await driver.l2_to_devmem(l2_addr=0x200, devmem_addr=0x200, length=size)

    # Verify pattern_b was transferred correctly
    result = await driver.read_bram(0x200, size)
    for i in range(size):
        assert abs(result[i] - pattern_b[i]) < 1e-6, \
            f"Offset test mismatch at [{i}]: expected {pattern_b[i]}, got {result[i]}"

    dut._log.info("test_l2_l1_base_addr_offset PASSED")
