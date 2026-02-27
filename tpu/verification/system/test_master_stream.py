"""
Unit tests for tpu_master_axi_stream (DMA read path: BRAM → host).

DUT: tpu_master_axi_stream (standalone; fifo4 is included in compile command)

Port reference (tpu_master_axi_stream.v):
  Inputs:  M_AXIS_ACLK, M_AXIS_ARESETN, M_AXIS_TREADY,
           data_to_ddr[31:0], len[31:0], read_en
  Outputs: M_AXIS_TVALID, M_AXIS_TDATA[31:0], M_AXIS_TSTRB[3:0],
           M_AXIS_TKEEP[3:0], M_AXIS_TLAST, done, read_pointer_stream[15:0]

Timing model (from rewritten RTL):
  - IDLE → FILL on read_en rising edge (no INIT_COUNTER delay).
  - FILL: issues BRAM reads (read_pointer_stream increments); waits for
    FIFO to have at least 1 entry (!fifo_empty) → STREAM.
  - STREAM: drives AXI handshake from FWFT FIFO. TVALID = !fifo_empty.
    TDATA = fifo_rd_data (combinational). Continues BRAM reads in parallel.
    beats_sent counts handshakes. TLAST on last beat. done → IDLE.

Driving strategy:
  After each RisingEdge, read read_pointer_stream and drive data_to_ddr
  with mem[ptr]. This models a 0-cycle combinatorial BRAM (no pipeline).
  The RTL's internal BRAM latency tracking (bram_data_valid) creates the
  effective 1-cycle latency the hardware expects.
"""

import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


def float_to_int(f):
    return struct.unpack('<I', struct.pack('<f', f))[0]


def int_to_float(i):
    return struct.unpack('<f', struct.pack('<I', i & 0xFFFFFFFF))[0]


async def reset_dut(dut):
    """Apply synchronous reset and configure static inputs."""
    dut.M_AXIS_ARESETN.value = 0
    dut.M_AXIS_TREADY.value = 1   # downstream always ready
    dut.read_en.value = 0
    dut.len.value = 0
    dut.data_to_ddr.value = 0
    await RisingEdge(dut.M_AXIS_ACLK)
    dut.M_AXIS_ARESETN.value = 1
    await RisingEdge(dut.M_AXIS_ACLK)


async def run_master_transfer(dut, mem, n, timeout_cycles=500):
    """
    Run a complete master AXI-Stream transfer.

    mem   : dict mapping address (int) → 32-bit data word (int)
    n     : number of words to transfer (len register value)
    Returns list of received M_AXIS_TDATA words in order.

    Driving protocol:
      After every RisingEdge we:
        1. Read read_pointer_stream (registered output, stable post-posedge).
        2. Drive data_to_ddr with mem[ptr] for the NEXT cycle.
        3. Check M_AXIS_TVALID / M_AXIS_TDATA / M_AXIS_TKEEP / done.
    """
    dut.len.value = n
    dut.read_en.value = 1
    await RisingEdge(dut.M_AXIS_ACLK)
    dut.read_en.value = 0   # pulse width = 1 cycle

    results = []
    for _ in range(timeout_cycles):
        await RisingEdge(dut.M_AXIS_ACLK)

        # Read outputs produced by this clock edge
        ptr    = int(dut.read_pointer_stream.value)
        tvalid = int(dut.M_AXIS_TVALID.value)
        tready = int(dut.M_AXIS_TREADY.value)
        done   = int(dut.done.value)

        # Drive data_to_ddr for the next cycle based on current pointer
        dut.data_to_ddr.value = int(mem.get(ptr, 0))

        if tvalid and tready:
            tdata = int(dut.M_AXIS_TDATA.value)
            tkeep = int(dut.M_AXIS_TKEEP.value)
            # Verify TKEEP is all-ones on every valid beat
            assert tkeep == 0xF, \
                f"TKEEP should be 0xF on valid beat, got {tkeep:#x}"
            results.append(tdata)

        if done:
            break

    return results


@cocotb.test()
async def test_master_read_n1(dut):
    """Read 1 word — minimum transfer edge case."""
    cocotb.start_soon(Clock(dut.M_AXIS_ACLK, 10, units="ns").start())
    await reset_dut(dut)

    n = 1
    mem = {0: float_to_int(99.0)}

    results = await run_master_transfer(dut, mem, n)

    assert len(results) == n, \
        f"Expected {n} word, got {len(results)}: {[hex(r) for r in results]}"
    expected = float_to_int(99.0)
    assert results[0] == expected, \
        f"Data mismatch: expected {expected:#010x}, got {results[0]:#010x}"
    dut._log.info("test_master_read_n1 PASSED")


@cocotb.test()
async def test_master_read_n8(dut):
    """
    Read 8 words through master stream.

    Verifies:
      - Correct number of words received (8)
      - Data values match the behavioural memory model
      - TKEEP driven on every beat
    """
    cocotb.start_soon(Clock(dut.M_AXIS_ACLK, 10, units="ns").start())
    await reset_dut(dut)

    n = 8
    mem = {i: float_to_int(float(i)) for i in range(n)}

    results = await run_master_transfer(dut, mem, n)

    assert len(results) == n, \
        f"Expected {n} words, got {len(results)}: {[hex(r) for r in results]}"

    for i, received in enumerate(results):
        expected = mem[i]
        assert received == expected, \
            f"Word {i}: expected {expected:#010x} ({int_to_float(expected):.4f}), " \
            f"got {received:#010x} ({int_to_float(received):.4f})"

    dut._log.info("test_master_read_n8 PASSED")


@cocotb.test()
async def test_master_read_n4(dut):
    """
    Read 4 words (N < FIFO depth). Verify correct data values.
    """
    cocotb.start_soon(Clock(dut.M_AXIS_ACLK, 10, units="ns").start())
    await reset_dut(dut)

    n = 4
    # Non-trivial float values to catch data corruption
    floats = [1.0, 2.5, -3.75, 0.0]
    mem = {i: float_to_int(floats[i]) for i in range(n)}

    results = await run_master_transfer(dut, mem, n)

    assert len(results) == n, \
        f"Expected {n} words, got {len(results)}: {[hex(r) for r in results]}"

    for i, received in enumerate(results):
        expected = mem[i]
        assert received == expected, \
            f"Word {i}: expected {expected:#010x} ({int_to_float(expected):.4f}), " \
            f"got {received:#010x} ({int_to_float(received):.4f})"

    dut._log.info("test_master_read_n4 PASSED")
