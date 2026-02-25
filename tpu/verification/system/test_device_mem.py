import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import numpy as np
from test_tpu import TpuRtlDriver, float_to_int, int_to_float


@cocotb.test()
async def test_devmem_write_read_integrity(dut):
    """Write pattern to device memory (mode 1), read back (mode 2), verify round-trip."""
    cocotb.start_soon(Clock(dut.s00_axi_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.s00_axis_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.m00_axis_aclk, 10, units="ns").start())

    driver = TpuRtlDriver(dut)
    await driver.reset()

    pattern = np.arange(16, dtype=np.float32)
    await driver.write_bram(0, pattern)
    result = await driver.read_bram(0, 16)

    for i in range(16):
        assert abs(result[i] - pattern[i]) < 1e-6, \
            f"Mismatch at index {i}: expected {pattern[i]}, got {result[i]}"
    dut._log.info("test_devmem_write_read_integrity PASSED")


@cocotb.test()
async def test_devmem_multiple_sizes(dut):
    """Write/read multiple sizes: 16, 64, 256 elements."""
    cocotb.start_soon(Clock(dut.s00_axi_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.s00_axis_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.m00_axis_aclk, 10, units="ns").start())

    driver = TpuRtlDriver(dut)
    await driver.reset()

    for size in [16, 64, 256]:
        pattern = np.arange(size, dtype=np.float32)
        await driver.write_bram(0, pattern)
        result = await driver.read_bram(0, size)

        for i in range(size):
            assert abs(result[i] - pattern[i]) < 1e-6, \
                f"Size {size}, mismatch at index {i}: expected {pattern[i]}, got {result[i]}"
        dut._log.info(f"  Size {size}: OK")

    dut._log.info("test_devmem_multiple_sizes PASSED")


@cocotb.test()
async def test_devmem_base_addr_offset(dut):
    """Write with addr_devmem=0x100, verify data is at correct offset."""
    cocotb.start_soon(Clock(dut.s00_axi_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.s00_axis_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.m00_axis_aclk, 10, units="ns").start())

    driver = TpuRtlDriver(dut)
    await driver.reset()

    # Write 16 elements at base offset 0x100
    pattern = np.array([1.0, -1.0, 0.5, -0.5, 2.0, 4.0, 8.0, 16.0,
                        32.0, 64.0, 128.0, 256.0, 0.25, 0.125, 0.0625, 0.03125],
                       dtype=np.float32)
    await driver.write_bram(0x100, pattern)
    result = await driver.read_bram(0x100, len(pattern))

    for i in range(len(pattern)):
        assert abs(result[i] - pattern[i]) < 1e-6, \
            f"Offset test mismatch at index {i}: expected {pattern[i]}, got {result[i]}"

    dut._log.info("test_devmem_base_addr_offset PASSED")
