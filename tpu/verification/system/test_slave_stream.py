"""
Unit tests for tpu_slave_axi_stream (DMA write path: host → BRAM).

DUT: tpu_slave_axi_stream (standalone, no tpu top)

Port reference (tpu_slave_axi_stream.v):
  Inputs:  S_AXIS_ACLK, S_AXIS_ARESETN, S_AXIS_TVALID, S_AXIS_TDATA[63:0],
           S_AXIS_TSTRB[7:0], S_AXIS_TLAST, len[31:0], write_en,
           tpu_mode_stream[2:0]
  Outputs: S_AXIS_TREADY, data_to_bram[31:0], data_to_iram[63:0],
           write_pointer_stream[15:0], done, data_valid

Key behaviour:
  - IDLE → WRITE_FIFO when S_AXIS_TVALID && write_en
  - data_valid = fifo_wren = S_AXIS_TVALID && S_AXIS_TREADY (combinational)
  - write_pointer_stream holds the *current* BRAM address; it increments on the
    next clock edge after a fifo_wren fires (and only when not the last word)
  - data_to_bram = S_AXIS_TDATA[31:0]  (lower 32 bits; slave is 64-bit wide)
"""

import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly


def float_to_int(f):
    return struct.unpack('<I', struct.pack('<f', f))[0]


async def reset_dut(dut):
    """Apply synchronous reset and configure common static inputs."""
    dut.S_AXIS_ARESETN.value = 0
    dut.S_AXIS_TVALID.value = 0
    dut.S_AXIS_TDATA.value = 0
    dut.S_AXIS_TSTRB.value = 0
    dut.S_AXIS_TLAST.value = 0
    dut.write_en.value = 1          # enable data writes (mode 1 = WRITE_DEVMEM)
    dut.tpu_mode_stream.value = 1   # mode 1 → data BRAM path
    dut.len.value = 0
    await RisingEdge(dut.S_AXIS_ACLK)
    dut.S_AXIS_ARESETN.value = 1
    await RisingEdge(dut.S_AXIS_ACLK)


async def stream_n_words(dut, values):
    """
    Drive N words onto the AXI-Stream slave and capture (write_pointer, data)
    pairs on every cycle that data_valid is asserted.

    Returns list of (ptr, data) tuples in order of acceptance.
    """
    n = len(values)
    writes = []

    for i, val in enumerate(values):
        # Present the 64-bit TDATA (lower 32 bits carry the data word)
        dut.S_AXIS_TDATA.value = int(val) & 0xFFFFFFFF
        dut.S_AXIS_TSTRB.value = 0xFF
        dut.S_AXIS_TLAST.value = 1 if i == n - 1 else 0
        dut.S_AXIS_TVALID.value = 1

        # Wait until the slave asserts TREADY (handshake completes)
        while True:
            await ReadOnly()
            tready = int(dut.S_AXIS_TREADY.value)
            data_valid = int(dut.data_valid.value)
            ptr = int(dut.write_pointer_stream.value)
            data = int(dut.data_to_bram.value)
            await RisingEdge(dut.S_AXIS_ACLK)
            if tready:
                if data_valid:
                    writes.append((ptr, data))
                break

    dut.S_AXIS_TVALID.value = 0
    return writes


@cocotb.test()
async def test_slave_write_n1(dut):
    """Write 1 value — edge case: single-word transfer."""
    cocotb.start_soon(Clock(dut.S_AXIS_ACLK, 10, units="ns").start())
    await reset_dut(dut)

    n = 1
    dut.len.value = n
    values = [float_to_int(42.0)]

    writes = await stream_n_words(dut, values)

    assert len(writes) == 1, f"Expected 1 write, got {len(writes)}: {writes}"
    assert writes[0][0] == 0, f"Expected address 0, got {writes[0][0]}"
    expected = float_to_int(42.0) & 0xFFFFFFFF
    assert writes[0][1] == expected, \
        f"Data mismatch: expected {expected:#010x}, got {writes[0][1]:#010x}"
    dut._log.info("test_slave_write_n1 PASSED")


@cocotb.test()
async def test_slave_write_n4(dut):
    """
    Write 4 values. Verify:
      - 4 handshakes fire
      - write_pointer_stream advances correctly (0, 1, 2, 3 in order)
      - data_to_bram matches input at each accepted cycle
    """
    cocotb.start_soon(Clock(dut.S_AXIS_ACLK, 10, units="ns").start())
    await reset_dut(dut)

    n = 4
    dut.len.value = n
    values = [float_to_int(float(i)) for i in range(n)]

    writes = await stream_n_words(dut, values)

    assert len(writes) == n, f"Expected {n} writes, got {len(writes)}: {writes}"

    for i, (ptr, data) in enumerate(writes):
        assert ptr == i, \
            f"Word {i}: expected pointer={i}, got pointer={ptr}. All writes: {writes}"
        expected = values[i] & 0xFFFFFFFF
        assert data == expected, \
            f"Word {i}: expected data={expected:#010x}, got {data:#010x}"

    dut._log.info("test_slave_write_n4 PASSED")


@cocotb.test()
async def test_slave_write_n8(dut):
    """
    Write 8 values (= FIFO depth).

    Bug A regression: the IDLE→WRITE_FIFO reset signal used to hold
    write_pointer_stream=0 for an extra cycle, causing the second word to
    overwrite address 0. After the fix (reset<=1'b0 on transition), the
    pointer must advance so address 0 is written exactly once.

    Assertions:
      - Exactly 8 writes fire
      - Address 0 appears exactly once
      - Pointers are 0,1,2,...,7 in order
      - Data values match
    """
    cocotb.start_soon(Clock(dut.S_AXIS_ACLK, 10, units="ns").start())
    await reset_dut(dut)

    n = 8
    dut.len.value = n
    values = [float_to_int(float(i)) for i in range(n)]

    writes = await stream_n_words(dut, values)

    # Bug A regression: address 0 must be written exactly once
    addr0_count = sum(1 for p, d in writes if p == 0)
    assert addr0_count == 1, \
        f"Bug A: address 0 written {addr0_count} times (expected 1). writes={writes}"

    assert len(writes) == n, \
        f"Expected {n} writes, got {len(writes)}: {writes}"

    for i, (ptr, data) in enumerate(writes):
        assert ptr == i, \
            f"Word {i}: expected pointer={i}, got pointer={ptr}. All writes: {writes}"
        expected = values[i] & 0xFFFFFFFF
        assert data == expected, \
            f"Word {i}: expected data={expected:#010x}, got {data:#010x}"

    dut._log.info("test_slave_write_n8 PASSED (Bug A regression: OK)")
