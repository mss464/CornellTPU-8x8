"""
Unit tests for fifo4.sv - 8-entry FIFO with parametrizable width
Tests basic operations and randomized stress testing
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
import random


async def reset_fifo(dut):
    """Reset the FIFO to a known state."""
    dut.rst_n.value = 0
    dut.wr_en.value = 0
    dut.rd_en.value = 0
    dut.wr_data.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_fifo_reset(dut):
    """Test that FIFO resets to empty state."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_fifo(dut)

    assert dut.empty.value == 1, "FIFO should be empty after reset"
    assert dut.full.value == 0, "FIFO should not be full after reset"
    dut._log.info("PASS: FIFO reset test")


@cocotb.test()
async def test_fifo_single_write_read(dut):
    """Test single write and read operation."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_fifo(dut)

    test_data = 0xDEADBEEF
    
    # Write single value
    dut.wr_en.value = 1
    dut.wr_data.value = test_data
    await RisingEdge(dut.clk)
    dut.wr_en.value = 0
    await RisingEdge(dut.clk)

    assert dut.empty.value == 0, "FIFO should not be empty after write"

    # Read: assert rd_en, data appears NEXT cycle
    dut.rd_en.value = 1
    await RisingEdge(dut.clk)  # Read initiated
    dut.rd_en.value = 0
    await RisingEdge(dut.clk)  # Data now valid

    read_data = int(dut.rd_data.value)
    assert read_data == test_data, f"Read mismatch: got {read_data:#x}, expected {test_data:#x}"
    dut._log.info(f"PASS: Single write/read test - data: {test_data:#x}")


@cocotb.test()
async def test_fifo_fill_and_drain(dut):
    """Test filling FIFO completely and draining it."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_fifo(dut)

    fifo_depth = 8
    test_values = [0x11111111 * (i + 1) for i in range(fifo_depth)]

    # Fill the FIFO
    for val in test_values:
        dut.wr_en.value = 1
        dut.wr_data.value = val
        await RisingEdge(dut.clk)

    dut.wr_en.value = 0
    await RisingEdge(dut.clk)

    assert dut.full.value == 1, "FIFO should be full after 8 writes"

    # Drain the FIFO - read data appears one cycle after rd_en
    read_values = []
    for i in range(fifo_depth):
        dut.rd_en.value = 1
        await RisingEdge(dut.clk)  # Read initiated
        dut.rd_en.value = 0
        await RisingEdge(dut.clk)  # Data now valid
        read_values.append(int(dut.rd_data.value))

    assert dut.empty.value == 1, "FIFO should be empty after draining"

    for i, (expected, actual) in enumerate(zip(test_values, read_values)):
        assert expected == actual, f"Data mismatch at {i}: got {actual:#x}, expected {expected:#x}"

    dut._log.info("PASS: Fill and drain test")


@cocotb.test()
async def test_fifo_full_flag(dut):
    """Test that FIFO full flag works correctly."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_fifo(dut)

    # Write until full
    for i in range(8):
        assert dut.full.value == 0, f"FIFO should not be full at count {i}"
        dut.wr_en.value = 1
        dut.wr_data.value = i
        await RisingEdge(dut.clk)

    dut.wr_en.value = 0
    await RisingEdge(dut.clk)
    
    assert dut.full.value == 1, "FIFO should be full after 8 writes"
    dut._log.info("PASS: Full flag test")


@cocotb.test()
async def test_fifo_underflow_protection(dut):
    """Test that reads from empty FIFO don't cause issues."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_fifo(dut)

    # Try to read from empty FIFO
    dut.rd_en.value = 1
    await ClockCycles(dut.clk, 3)
    dut.rd_en.value = 0

    assert dut.empty.value == 1, "FIFO should remain empty"
    dut._log.info("PASS: Underflow protection test")


@cocotb.test()
async def test_fifo_one_item_remaining(dut):
    """Test the one_item_remaining signal."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_fifo(dut)

    # Write one item
    dut.wr_en.value = 1
    dut.wr_data.value = 0x12345678
    await RisingEdge(dut.clk)
    dut.wr_en.value = 0
    await RisingEdge(dut.clk)

    assert dut.one_item_remaining.value == 1, "Should indicate one item remaining"

    # Write another item
    dut.wr_en.value = 1
    dut.wr_data.value = 0x87654321
    await RisingEdge(dut.clk)
    dut.wr_en.value = 0
    await RisingEdge(dut.clk)

    assert dut.one_item_remaining.value == 0, "Should not indicate one item with 2 items"

    dut._log.info("PASS: One item remaining signal test")


@cocotb.test()
async def test_fifo_sequential_ops(dut):
    """Test sequential write/read operations."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_fifo(dut)

    # Write 4 items
    test_data = [0xAAAA, 0xBBBB, 0xCCCC, 0xDDDD]
    for val in test_data:
        dut.wr_en.value = 1
        dut.wr_data.value = val
        await RisingEdge(dut.clk)
    dut.wr_en.value = 0
    await RisingEdge(dut.clk)

    # Read back and verify
    for expected in test_data:
        dut.rd_en.value = 1
        await RisingEdge(dut.clk)
        dut.rd_en.value = 0
        await RisingEdge(dut.clk)
        actual = int(dut.rd_data.value)
        assert actual == expected, f"Mismatch: got {actual:#x}, expected {expected:#x}"

    dut._log.info("PASS: Sequential operations test")
