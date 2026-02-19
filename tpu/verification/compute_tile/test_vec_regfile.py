"""Unit tests for vec_regfile.sv - Vector register file."""

import cocotb
from cocotb.triggers import RisingEdge
from cocotb.clock import Clock
import struct

def float_to_fp32(f):
    """Convert Python float to 32-bit integer representation."""
    return struct.unpack('>I', struct.pack('>f', f))[0]

def fp32_to_float(bits):
    """Convert 32-bit integer to Python float."""
    return struct.unpack('>f', struct.pack('>I', bits))[0]

@cocotb.test()
async def test_regfile_reset(dut):
    """Test that reset initializes all registers to zero."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Read all registers and verify they are zero
    for reg in range(8):
        dut.rd_addr_a.value = reg
        await RisingEdge(dut.clk)

        for elem in range(8):
            elem_bits = int(dut.rd_data_a.value) >> (elem * 32) & 0xFFFFFFFF
            assert elem_bits == 0, f"Register {reg} element {elem} not zero after reset"

    dut._log.info("PASS: All registers initialized to zero")


@cocotb.test()
async def test_regfile_write_read(dut):
    """Test basic write and read operations."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.rst_n.value = 0
    dut.wr_en.value = 0
    dut.wr_addr.value = 0
    dut.wr_data.value = 0
    dut.rd_addr_a.value = 0
    dut.rd_addr_b.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Write to register 0
    test_data = 0
    for i in range(8):
        elem_val = float_to_fp32(float(i + 1))
        test_data |= elem_val << (i * 32)

    dut.wr_en.value = 1
    dut.wr_addr.value = 0
    dut.wr_data.value = test_data
    await RisingEdge(dut.clk)
    dut.wr_en.value = 0

    # Read from register 0
    dut.rd_addr_a.value = 0
    await RisingEdge(dut.clk)

    # Verify data
    read_data = int(dut.rd_data_a.value)
    for i in range(8):
        elem_bits = (read_data >> (i * 32)) & 0xFFFFFFFF
        elem_val = fp32_to_float(elem_bits)
        expected = float(i + 1)
        assert abs(elem_val - expected) < 0.01, f"Element {i}: got {elem_val}, expected {expected}"

    dut._log.info("PASS: Register file write/read")


@cocotb.test()
async def test_regfile_dual_port(dut):
    """Test dual-port simultaneous reads."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.wr_en.value = 0
    dut.wr_addr.value = 0
    dut.wr_data.value = 0
    dut.rd_addr_a.value = 0
    dut.rd_addr_b.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Write to register 1 and 2
    for reg in [1, 2]:
        test_data = 0
        for i in range(8):
            val = float_to_fp32(float(reg * 10 + i))
            test_data |= val << (i * 32)

        dut.wr_en.value = 1
        dut.wr_addr.value = reg
        dut.wr_data.value = test_data
        await RisingEdge(dut.clk)

    dut.wr_en.value = 0

    # Simultaneous read from both ports
    dut.rd_addr_a.value = 1
    dut.rd_addr_b.value = 2
    await RisingEdge(dut.clk)

    # Verify port A (register 1)
    read_data_a = int(dut.rd_data_a.value)
    for i in range(8):
        elem = fp32_to_float((read_data_a >> (i * 32)) & 0xFFFFFFFF)
        expected = float(10 + i)
        assert abs(elem - expected) < 0.01, f"Port A element {i}: got {elem}, expected {expected}"

    # Verify port B (register 2)
    read_data_b = int(dut.rd_data_b.value)
    for i in range(8):
        elem = fp32_to_float((read_data_b >> (i * 32)) & 0xFFFFFFFF)
        expected = float(20 + i)
        assert abs(elem - expected) < 0.01, f"Port B element {i}: got {elem}, expected {expected}"

    dut._log.info("PASS: Dual-port simultaneous read")


@cocotb.test()
async def test_regfile_all_registers(dut):
    """Test writing and reading all 8 registers."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.wr_en.value = 0
    dut.wr_addr.value = 0
    dut.wr_data.value = 0
    dut.rd_addr_a.value = 0
    dut.rd_addr_b.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Write unique pattern to each register
    for reg in range(8):
        test_data = 0
        for elem in range(8):
            val = float_to_fp32(float(reg * 100 + elem))
            test_data |= val << (elem * 32)

        dut.wr_en.value = 1
        dut.wr_addr.value = reg
        dut.wr_data.value = test_data
        await RisingEdge(dut.clk)

    dut.wr_en.value = 0

    # Read back and verify each register
    for reg in range(8):
        dut.rd_addr_a.value = reg
        await RisingEdge(dut.clk)

        read_data = int(dut.rd_data_a.value)
        for elem in range(8):
            elem_val = fp32_to_float((read_data >> (elem * 32)) & 0xFFFFFFFF)
            expected = float(reg * 100 + elem)
            assert abs(elem_val - expected) < 0.01, \
                f"Register {reg} element {elem}: got {elem_val}, expected {expected}"

    dut._log.info("PASS: All 8 registers write/read")


@cocotb.test()
async def test_regfile_write_disabled(dut):
    """Test that writes are ignored when wr_en is low."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.wr_en.value = 0
    dut.wr_addr.value = 0
    dut.wr_data.value = 0
    dut.rd_addr_a.value = 0
    dut.rd_addr_b.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Write with wr_en = 1
    test_data = float_to_fp32(42.0)
    dut.wr_en.value = 1
    dut.wr_addr.value = 3
    dut.wr_data.value = test_data << 0  # Just first element
    await RisingEdge(dut.clk)

    # Try to overwrite with wr_en = 0
    dut.wr_en.value = 0
    dut.wr_data.value = float_to_fp32(99.0)
    await RisingEdge(dut.clk)

    # Read back - should still be 42.0
    dut.rd_addr_a.value = 3
    await RisingEdge(dut.clk)

    read_data = int(dut.rd_data_a.value)
    elem_val = fp32_to_float(read_data & 0xFFFFFFFF)
    assert abs(elem_val - 42.0) < 0.01, f"Write occurred when wr_en=0: got {elem_val}"

    dut._log.info("PASS: Writes disabled when wr_en=0")
