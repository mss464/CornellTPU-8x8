"""
test_tma.py — Unit tests for the TMA engine inside l2_tile.sv.

Tests two request paths:
  - Host-controlled (start_dm_to_l2 / start_l2_to_dm + xfer_* params)
  - TMA instruction (tma_req + tma_dir/tma_dm_base/tma_l2_base/tma_len)

Device memory is modeled in Python (dict); the L2 SRAM is the internal
blk_mem_gen_3 behavioral model. Port A (ct_addr_a, ct_en_a, ct_we_a,
ct_dout_a) is used to pre-load / verify L2 contents.

TMA instruction bit encoding (MODE=2):
  [63:62]=2  [61]=dir  [60:45]=dm_addr  [44:30]=l2_addr  [29:14]=len
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge
import struct

# ============================================================================
# Helpers
# ============================================================================

def float_to_bits(f):
    return struct.unpack('>I', struct.pack('>f', f))[0]


async def reset_dut(dut):
    """Apply reset and drive all inputs to known-safe defaults."""
    dut.rst_n.value = 0
    dut.ct_addr_a.value = 0
    dut.ct_din_a.value  = 0
    dut.ct_en_a.value   = 0
    dut.ct_we_a.value   = 0
    dut.dm_dout.value   = 0
    dut.start_dm_to_l2.value = 0
    dut.start_l2_to_dm.value = 0
    dut.xfer_dm_base.value   = 0
    dut.xfer_l2_base.value   = 0
    dut.xfer_len.value       = 0
    dut.tma_req.value        = 0
    dut.tma_dir.value        = 0
    dut.tma_dm_base.value    = 0
    dut.tma_l2_base.value    = 0
    dut.tma_len.value        = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def run_transfer(dut, devmem, timeout=500):
    """
    Advance simulation for one DM↔L2 transfer while serving the device-memory
    port B from the Python dict.

    DM→L2 timing (FallingEdge strategy):
      tma_engine issues devmem reads combinationally each cycle. Python models
      the 1-cycle registered devmem output by driving dm_dout at FallingEdge
      (midpoint between posedges), so the value is stable at the NEXT posedge
      when the L2 BRAM always@(posedge) captures sram_din_b = dm_dout.

        RisingEdge N  → sample dm_addr = A  (based on rd_count pre-NBA)
        FallingEdge N → drive dm_dout = devmem[A]
        RisingEdge N+1 → BRAM writes dm_dout to L2[l2_wr_addr_d1]

      Driving at FallingEdge guarantees a full half-period for the VPI write to
      propagate combinationally before the next BRAM posedge capture.

    L2→DM: dm_din and dm_we are RTL-driven; Python just captures writes.
    """
    for _ in range(timeout):
        await RisingEdge(dut.clk)

        dm_en   = int(dut.dm_en.value)
        dm_we   = int(dut.dm_we.value)
        dm_addr = int(dut.dm_addr.value)

        # Capture devmem writes (L2→DM direction)
        if dm_en and dm_we:
            devmem[dm_addr] = int(dut.dm_din.value)

        if int(dut.xfer_done.value) or int(dut.tma_done.value):
            return

        # Drive dm_dout at FallingEdge: stable at the NEXT posedge when the
        # L2 BRAM always@(posedge) captures sram_din_b = dm_dout.
        await FallingEdge(dut.clk)
        if dm_en and not dm_we:
            dut.dm_dout.value = devmem.get(dm_addr, 0)

    raise AssertionError(f"Transfer timed out after {timeout} cycles")


async def read_l2_word(dut, addr):
    """
    Read one word from L2 SRAM via Port A.
    blk_mem_gen_3 has 1-cycle registered latency: address captured at posedge N,
    data valid (from NBA) when cocotb resumes after posedge N+1.
    """
    dut.ct_addr_a.value = addr
    dut.ct_en_a.value   = 1
    dut.ct_we_a.value   = 0
    await RisingEdge(dut.clk)    # BRAM captures addr at posedge N
    await RisingEdge(dut.clk)    # data valid after posedge N+1 NBA
    data = int(dut.ct_dout_a.value)
    dut.ct_en_a.value = 0
    return data


async def write_l2_word(dut, addr, data):
    """Write one word to L2 SRAM via Port A."""
    dut.ct_addr_a.value = addr
    dut.ct_din_a.value  = data
    dut.ct_en_a.value   = 1
    dut.ct_we_a.value   = 1
    await RisingEdge(dut.clk)
    dut.ct_en_a.value = 0
    dut.ct_we_a.value = 0
    await RisingEdge(dut.clk)


# ============================================================================
# Test 1: Host-controlled DM→L2 transfer (regression: existing mode 5 path)
# ============================================================================
@cocotb.test()
async def test_host_dm_to_l2(dut):
    """Host-controlled DM→L2 block copy (start_dm_to_l2 / mode 5 path)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    n = 8
    dm_base = 0
    l2_base = 0

    src_vals = [float_to_bits(float(i + 1)) for i in range(n)]
    devmem   = {dm_base + i: src_vals[i] for i in range(n)}

    # Pulse start_dm_to_l2
    dut.xfer_dm_base.value   = dm_base
    dut.xfer_l2_base.value   = l2_base
    dut.xfer_len.value       = n
    dut.start_dm_to_l2.value = 1
    await RisingEdge(dut.clk)
    dut.start_dm_to_l2.value = 0

    await run_transfer(dut, devmem)

    # Verify L2 contents via Port A
    for i in range(n):
        got = await read_l2_word(dut, l2_base + i)
        assert got == src_vals[i], \
            f"DM→L2[{i}]: expected 0x{src_vals[i]:08x}, got 0x{got:08x}"

    dut._log.info("PASS: test_host_dm_to_l2")


# ============================================================================
# Test 2: Host-controlled L2→DM transfer (regression: existing mode 6 path)
# ============================================================================
@cocotb.test()
async def test_host_l2_to_dm(dut):
    """Host-controlled L2→DM block copy (start_l2_to_dm / mode 6 path)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    n = 8
    dm_base = 100
    l2_base = 50

    # Pre-populate L2 via Port A
    src_vals = [float_to_bits(float(i * 3 + 5)) for i in range(n)]
    for i in range(n):
        await write_l2_word(dut, l2_base + i, src_vals[i])

    devmem = {}

    # Pulse start_l2_to_dm
    dut.xfer_dm_base.value   = dm_base
    dut.xfer_l2_base.value   = l2_base
    dut.xfer_len.value       = n
    dut.start_l2_to_dm.value = 1
    await RisingEdge(dut.clk)
    dut.start_l2_to_dm.value = 0

    await run_transfer(dut, devmem)

    for i in range(n):
        addr = dm_base + i
        assert addr in devmem, f"Missing devmem write at address {addr}"
        assert devmem[addr] == src_vals[i], \
            f"L2→DM[{i}]: expected 0x{src_vals[i]:08x}, got 0x{devmem[addr]:08x}"

    dut._log.info("PASS: test_host_l2_to_dm")


# ============================================================================
# Test 3: TMA-instruction-triggered DM→L2 transfer
# ============================================================================
@cocotb.test()
async def test_tma_dm_to_l2(dut):
    """TMA instruction DM→L2: tma_req with dir=0 triggers transfer."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    n = 8
    dm_base = 200
    l2_base = 10

    src_vals = [float_to_bits(float(i * 2 + 1)) for i in range(n)]
    devmem   = {dm_base + i: src_vals[i] for i in range(n)}

    # Pulse tma_req with direction=0 (DM→L2)
    dut.tma_dir.value     = 0
    dut.tma_dm_base.value = dm_base
    dut.tma_l2_base.value = l2_base
    dut.tma_len.value     = n
    dut.tma_req.value     = 1
    await RisingEdge(dut.clk)
    dut.tma_req.value = 0

    await run_transfer(dut, devmem)

    for i in range(n):
        got = await read_l2_word(dut, l2_base + i)
        assert got == src_vals[i], \
            f"TMA DM→L2[{i}]: expected 0x{src_vals[i]:08x}, got 0x{got:08x}"

    dut._log.info("PASS: test_tma_dm_to_l2")


# ============================================================================
# Test 4: TMA-instruction-triggered L2→DM transfer
# ============================================================================
@cocotb.test()
async def test_tma_l2_to_dm(dut):
    """TMA instruction L2→DM: tma_req with dir=1 triggers transfer."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    n = 8
    dm_base = 300
    l2_base = 20

    # Pre-populate L2 via Port A
    src_vals = [float_to_bits(float(i * 5 + 2)) for i in range(n)]
    for i in range(n):
        await write_l2_word(dut, l2_base + i, src_vals[i])

    devmem = {}

    # Pulse tma_req with direction=1 (L2→DM)
    dut.tma_dir.value     = 1
    dut.tma_dm_base.value = dm_base
    dut.tma_l2_base.value = l2_base
    dut.tma_len.value     = n
    dut.tma_req.value     = 1
    await RisingEdge(dut.clk)
    dut.tma_req.value = 0

    await run_transfer(dut, devmem)

    for i in range(n):
        addr = dm_base + i
        assert addr in devmem, f"Missing devmem write at address {addr}"
        assert devmem[addr] == src_vals[i], \
            f"TMA L2→DM[{i}]: expected 0x{src_vals[i]:08x}, got 0x{devmem[addr]:08x}"

    dut._log.info("PASS: test_tma_l2_to_dm")


# ============================================================================
# Test 5: Done signal isolation — host uses xfer_done, TMA uses tma_done
# ============================================================================
@cocotb.test()
async def test_done_signal_isolation(dut):
    """xfer_done fires for host transfers; tma_done fires for TMA transfers."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    n = 4

    # --- Host transfer: xfer_done must fire, tma_done must NOT ---
    devmem = {i: float_to_bits(float(i + 100)) for i in range(n)}

    dut.xfer_dm_base.value   = 0
    dut.xfer_l2_base.value   = 0
    dut.xfer_len.value       = n
    dut.start_dm_to_l2.value = 1
    await RisingEdge(dut.clk)
    dut.start_dm_to_l2.value = 0

    xfer_fired = False
    tma_fired  = False
    for _ in range(200):
        await RisingEdge(dut.clk)
        dm_en   = int(dut.dm_en.value)
        dm_we   = int(dut.dm_we.value)
        dm_addr = int(dut.dm_addr.value)
        if dm_en and dm_we:
            devmem[dm_addr] = int(dut.dm_din.value)
        if int(dut.xfer_done.value):
            xfer_fired = True
        if int(dut.tma_done.value):
            tma_fired = True
        if xfer_fired:
            break
        await FallingEdge(dut.clk)
        if dm_en and not dm_we:
            dut.dm_dout.value = devmem.get(dm_addr, 0)

    assert xfer_fired, "xfer_done should fire for host transfer"
    assert not tma_fired, "tma_done must NOT fire for host transfer"

    # --- TMA transfer: tma_done must fire, xfer_done must NOT ---
    await reset_dut(dut)
    devmem2 = {i + 50: float_to_bits(float(i + 200)) for i in range(n)}

    dut.tma_dir.value     = 0
    dut.tma_dm_base.value = 50
    dut.tma_l2_base.value = 100
    dut.tma_len.value     = n
    dut.tma_req.value     = 1
    await RisingEdge(dut.clk)
    dut.tma_req.value = 0

    xfer_fired = False
    tma_fired  = False
    for _ in range(200):
        await RisingEdge(dut.clk)
        dm_en   = int(dut.dm_en.value)
        dm_we   = int(dut.dm_we.value)
        dm_addr = int(dut.dm_addr.value)
        if dm_en and dm_we:
            devmem2[dm_addr] = int(dut.dm_din.value)
        if int(dut.xfer_done.value):
            xfer_fired = True
        if int(dut.tma_done.value):
            tma_fired = True
        if tma_fired:
            break
        await FallingEdge(dut.clk)
        if dm_en and not dm_we:
            dut.dm_dout.value = devmem2.get(dm_addr, 0)

    assert tma_fired, "tma_done should fire for TMA transfer"
    assert not xfer_fired, "xfer_done must NOT fire for TMA transfer"

    dut._log.info("PASS: test_done_signal_isolation")
