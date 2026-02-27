"""Unit tests for pc.sv - Program Counter module"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge


async def reset_pc(dut):
    """Reset the PC to a known state."""
    dut.rst_n.value = 0
    dut.PC_enable.value = 0
    dut.PC_load.value = 0
    dut.PC_load_val.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


@cocotb.test()
async def test_pc_reset(dut):
    """Test PC reset behavior."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_pc(dut)

    assert int(dut.PC.value) == 0, f"PC should be 0 after reset, got {int(dut.PC.value)}"
    dut._log.info("PASS: PC reset test")


@cocotb.test()
async def test_pc_increment(dut):
    """Test PC increment - signal setup before clock edge."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_pc(dut)
    assert int(dut.PC.value) == 0, "PC should start at 0"

    # Set PC_enable before edge, increment happens on edge
    # Use falling edge to set signals, rising edge triggers PC update
    for i in range(10):
        await FallingEdge(dut.clk)  # Mid-cycle, set up signals
        dut.PC_enable.value = 1
        await RisingEdge(dut.clk)  # PC increments here
    
    await FallingEdge(dut.clk)
    dut.PC_enable.value = 0
    await RisingEdge(dut.clk)
    
    pc_val = int(dut.PC.value)
    assert pc_val == 10, f"PC should be 10 after 10 increments, got {pc_val}"
    dut._log.info("PASS: PC increment test")


@cocotb.test()
async def test_pc_load(dut):
    """Test PC load operation."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_pc(dut)

    # Set up load before rising edge
    await FallingEdge(dut.clk)
    dut.PC_load.value = 1
    dut.PC_load_val.value = 0x55
    await RisingEdge(dut.clk)  # Load happens here
    
    await FallingEdge(dut.clk)
    dut.PC_load.value = 0
    await RisingEdge(dut.clk)

    pc_val = int(dut.PC.value)
    assert pc_val == 0x55, f"PC should be 0x55, got {pc_val:#x}"
    dut._log.info("PASS: PC load test")


@cocotb.test()
async def test_pc_hold(dut):
    """Test PC holds when not enabled."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_pc(dut)

    # Increment 5 times
    for _ in range(5):
        await FallingEdge(dut.clk)
        dut.PC_enable.value = 1
        await RisingEdge(dut.clk)
    
    await FallingEdge(dut.clk)
    dut.PC_enable.value = 0
    await RisingEdge(dut.clk)

    held_val = int(dut.PC.value)
    assert held_val == 5, f"PC should be 5, got {held_val}"

    # Wait and verify hold
    for _ in range(5):
        await RisingEdge(dut.clk)
        assert int(dut.PC.value) == held_val, "PC should hold"

    dut._log.info("PASS: PC hold test")


@cocotb.test()
async def test_pc_load_priority(dut):
    """Test PC_load has priority over PC_enable."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_pc(dut)

    # Increment to move away from 0
    for _ in range(5):
        await FallingEdge(dut.clk)
        dut.PC_enable.value = 1
        await RisingEdge(dut.clk)

    # Both load and enable - load wins
    await FallingEdge(dut.clk)
    dut.PC_load.value = 1
    dut.PC_enable.value = 1
    dut.PC_load_val.value = 0x42
    await RisingEdge(dut.clk)
    
    await FallingEdge(dut.clk)
    dut.PC_load.value = 0
    dut.PC_enable.value = 0
    await RisingEdge(dut.clk)

    pc_val = int(dut.PC.value)
    assert pc_val == 0x42, f"PC should be 0x42 (load wins), got {pc_val:#x}"
    dut._log.info("PASS: PC load priority test")


@cocotb.test()
async def test_pc_wrap_around(dut):
    """Test PC wraps around at max value (8-bit)."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    await reset_pc(dut)

    # Load to 0xFC (4 away from wrap)
    await FallingEdge(dut.clk)
    dut.PC_load.value = 1
    dut.PC_load_val.value = 0xFC
    await RisingEdge(dut.clk)
    
    await FallingEdge(dut.clk)
    dut.PC_load.value = 0
    await RisingEdge(dut.clk)  # Now PC should be 0xFC
    
    assert int(dut.PC.value) == 0xFC, f"PC should be 0xFC after load, got {int(dut.PC.value):#x}"
    
    # Enable and increment 6 times: 0xFC -> FD -> FE -> FF -> 00 -> 01 -> 02
    for i in range(6):
        await FallingEdge(dut.clk)
        dut.PC_enable.value = 1
        await RisingEdge(dut.clk)
    
    await FallingEdge(dut.clk)
    dut.PC_enable.value = 0
    await RisingEdge(dut.clk)
    
    pc_val = int(dut.PC.value)
    # 0xFC + 6 = 0x102, but 8-bit wrap gives 0x02
    assert pc_val == 0x02, f"PC should be 0x02 after wrap, got {pc_val:#x}"
    
    dut._log.info("PASS: PC wrap around test")
