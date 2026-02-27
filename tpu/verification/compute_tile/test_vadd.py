"""Unit tests for vadd.sv - Simple vector addition module"""

import cocotb
from cocotb.triggers import Timer
import random


@cocotb.test()
async def test_vadd_zero_inputs(dut):
    """Test addition with zero inputs."""
    dut.a.value = 0
    dut.b.value = 0
    await Timer(1, unit="ns")
    result = int(dut.sum.value)
    assert result == 0, f"0 + 0 should be 0, got {result}"
    dut._log.info("PASS: Zero inputs test")


@cocotb.test()
async def test_vadd_basic_addition(dut):
    """Test basic addition operations."""
    test_cases = [(1, 1, 2), (5, 3, 8), (100, 200, 300), (0xFFFF, 1, 0x10000)]
    for a, b, expected in test_cases:
        dut.a.value = a
        dut.b.value = b
        await Timer(1, unit="ns")
        result = int(dut.sum.value)
        assert result == expected, f"{a} + {b} should be {expected}, got {result}"
    dut._log.info("PASS: Basic addition test")


@cocotb.test()
async def test_vadd_max_values(dut):
    """Test addition with maximum 32-bit values."""
    max_val = 0xFFFFFFFF
    dut.a.value = max_val
    dut.b.value = 0
    await Timer(1, unit="ns")
    assert int(dut.sum.value) == max_val
    dut.a.value = max_val
    dut.b.value = 1
    await Timer(1, unit="ns")
    assert int(dut.sum.value) == 0, "Max + 1 should wrap to 0"
    dut._log.info("PASS: Max values test")


@cocotb.test()
async def test_vadd_randomized(dut):
    """Randomized stress test for vector addition."""
    random.seed(54321)
    for _ in range(100):
        a = random.randint(0, 0xFFFFFFFF)
        b = random.randint(0, 0xFFFFFFFF)
        expected = (a + b) & 0xFFFFFFFF
        dut.a.value = a
        dut.b.value = b
        await Timer(1, unit="ns")
        result = int(dut.sum.value)
        assert result == expected, f"{a:#x} + {b:#x} mismatch"
    dut._log.info("PASS: Randomized vadd test")
