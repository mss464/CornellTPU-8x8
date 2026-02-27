"""
Unit tests for fifo4.sv — FWFT synchronous FIFO with flush.

Key behavioral differences from old fifo4:
  - FWFT: rd_data is valid combinationally when !empty (no 1-cycle delay)
  - flush port: synchronous clear (active high)
  - almost_full replaces one_item_remaining
  - Default depth = 64 (was 8)
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles
import random


FIFO_DEPTH = 64


async def reset_fifo(dut):
    """Reset the FIFO to a known state."""
    dut.rst_n.value = 0
    dut.wr_en.value = 0
    dut.rd_en.value = 0
    dut.wr_data.value = 0
    dut.flush.value = 0
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
    assert dut.almost_full.value == 0, "FIFO should not be almost_full after reset"
    dut._log.info("PASS: FIFO reset test")


@cocotb.test()
async def test_fifo_single_write_read(dut):
    """Test single write and read — FWFT: data valid same cycle as !empty."""
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

    # FWFT: rd_data is valid NOW (combinational from mem[rptr])
    read_data = int(dut.rd_data.value)
    assert read_data == test_data, f"FWFT mismatch: got {read_data:#x}, expected {test_data:#x}"

    # Consume: assert rd_en for 1 cycle
    dut.rd_en.value = 1
    await RisingEdge(dut.clk)
    dut.rd_en.value = 0
    await RisingEdge(dut.clk)

    assert dut.empty.value == 1, "FIFO should be empty after read"
    dut._log.info(f"PASS: Single write/read test - data: {test_data:#x}")


@cocotb.test()
async def test_fifo_fill_and_drain(dut):
    """Test filling FIFO completely and draining it (FWFT read)."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_fifo(dut)

    test_values = [(0x11110000 + i) for i in range(FIFO_DEPTH)]

    # Fill the FIFO
    for val in test_values:
        dut.wr_en.value = 1
        dut.wr_data.value = val
        await RisingEdge(dut.clk)

    dut.wr_en.value = 0
    await RisingEdge(dut.clk)

    assert dut.full.value == 1, f"FIFO should be full after {FIFO_DEPTH} writes"

    # Drain the FIFO — FWFT: rd_data valid when !empty.
    # After rd_en+posedge, rptr advances and new rd_data settles next edge.
    read_values = []
    for i in range(FIFO_DEPTH):
        # Read FWFT output, then consume
        read_values.append(int(dut.rd_data.value))
        dut.rd_en.value = 1
        await RisingEdge(dut.clk)
        dut.rd_en.value = 0
        await RisingEdge(dut.clk)  # let rptr settle → new rd_data valid

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
    for i in range(FIFO_DEPTH):
        assert dut.full.value == 0, f"FIFO should not be full at count {i}"
        dut.wr_en.value = 1
        dut.wr_data.value = i
        await RisingEdge(dut.clk)

    dut.wr_en.value = 0
    await RisingEdge(dut.clk)

    assert dut.full.value == 1, f"FIFO should be full after {FIFO_DEPTH} writes"
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
async def test_fifo_almost_full(dut):
    """Test the almost_full signal (asserted when count >= DEPTH-1)."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_fifo(dut)

    # Write DEPTH-2 items — should NOT be almost_full
    for i in range(FIFO_DEPTH - 2):
        dut.wr_en.value = 1
        dut.wr_data.value = i
        await RisingEdge(dut.clk)

    dut.wr_en.value = 0
    await RisingEdge(dut.clk)

    assert dut.almost_full.value == 0, \
        f"Should not be almost_full with {FIFO_DEPTH - 2} items"

    # Write one more (DEPTH-1 items) — should be almost_full
    dut.wr_en.value = 1
    dut.wr_data.value = 0xFF
    await RisingEdge(dut.clk)
    dut.wr_en.value = 0
    await RisingEdge(dut.clk)

    assert dut.almost_full.value == 1, \
        f"Should be almost_full with {FIFO_DEPTH - 1} items"

    # Write one more (full) — should still be almost_full (count >= DEPTH-1)
    dut.wr_en.value = 1
    dut.wr_data.value = 0xFE
    await RisingEdge(dut.clk)
    dut.wr_en.value = 0
    await RisingEdge(dut.clk)

    assert dut.almost_full.value == 1, "Should be almost_full when full"
    assert dut.full.value == 1, "Should be full"

    dut._log.info("PASS: almost_full signal test")


@cocotb.test()
async def test_fifo_flush(dut):
    """Test synchronous flush clears the FIFO."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_fifo(dut)

    # Write some items
    for i in range(10):
        dut.wr_en.value = 1
        dut.wr_data.value = 0xAA + i
        await RisingEdge(dut.clk)
    dut.wr_en.value = 0
    await RisingEdge(dut.clk)

    assert dut.empty.value == 0, "FIFO should not be empty before flush"

    # Assert flush for 1 cycle
    dut.flush.value = 1
    await RisingEdge(dut.clk)
    dut.flush.value = 0
    await RisingEdge(dut.clk)

    assert dut.empty.value == 1, "FIFO should be empty after flush"
    assert dut.full.value == 0, "FIFO should not be full after flush"

    # Verify FIFO is usable after flush
    dut.wr_en.value = 1
    dut.wr_data.value = 0xCAFEBABE
    await RisingEdge(dut.clk)
    dut.wr_en.value = 0
    await RisingEdge(dut.clk)

    assert dut.empty.value == 0, "FIFO should accept writes after flush"
    read_data = int(dut.rd_data.value)
    assert read_data == 0xCAFEBABE, f"Post-flush data mismatch: {read_data:#x}"

    dut._log.info("PASS: Flush test")


@cocotb.test()
async def test_fifo_fwft_timing(dut):
    """Verify FWFT: rd_data is valid same cycle as !empty, no extra delay."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_fifo(dut)

    # Write 3 items
    test_data = [0xAAAA0001, 0xBBBB0002, 0xCCCC0003]
    for val in test_data:
        dut.wr_en.value = 1
        dut.wr_data.value = val
        await RisingEdge(dut.clk)
    dut.wr_en.value = 0
    await RisingEdge(dut.clk)

    # FWFT: first word should be visible immediately without rd_en
    assert dut.empty.value == 0
    first = int(dut.rd_data.value)
    assert first == test_data[0], \
        f"FWFT first word: got {first:#x}, expected {test_data[0]:#x}"

    # Read and check each word: FWFT means rd_data is valid BEFORE rd_en.
    # After rd_en fires on a posedge, rptr advances; need one more edge for
    # the new combinational rd_data to be visible in cocotb.
    for i in range(3):
        rd = int(dut.rd_data.value)
        assert rd == test_data[i], \
            f"FWFT word {i}: got {rd:#x}, expected {test_data[i]:#x}"
        dut.rd_en.value = 1
        await RisingEdge(dut.clk)
        dut.rd_en.value = 0
        await RisingEdge(dut.clk)  # let rptr settle → new rd_data valid

    assert dut.empty.value == 1, "Should be empty after reading all 3"

    dut._log.info("PASS: FWFT timing test")


@cocotb.test()
async def test_fifo_sequential_ops(dut):
    """Test sequential write/read operations with FWFT semantics."""
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

    # Read back with FWFT — data valid before rd_en
    for expected in test_data:
        actual = int(dut.rd_data.value)
        assert actual == expected, f"Mismatch: got {actual:#x}, expected {expected:#x}"
        dut.rd_en.value = 1
        await RisingEdge(dut.clk)
        dut.rd_en.value = 0
        await RisingEdge(dut.clk)  # let rptr settle → new rd_data valid

    dut._log.info("PASS: Sequential operations test")
