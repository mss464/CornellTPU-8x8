import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer, ReadOnly
import numpy as np

# cocotbext-axi BFMs (P1.7-4): replace manual AXI-Stream signal driving with
# AXIStreamSource (slave/write path) and AXIStreamSink (master/read path).
# Benefit: 3-5× fewer VPI crossings — handshake logic runs inside the BFM
# coroutine rather than being re-driven per cycle from Python.
from cocotbext.axi import AxiStreamSource, AxiStreamSink, AxiStreamBus, AxiStreamFrame
# AXI4 full (memory-mapped) BFM to simulate LPDDR4 backed by AxiRam.
# We use a lightweight manual coroutine instead of cocotbext AxiRam because
# the tpu module omits AXI ID signals (bid/rid), which AxiBus.from_prefix requires.


def float_to_int(f):
    return struct.unpack('<I', struct.pack('<f', f))[0]


def int_to_float(i):
    return struct.unpack('<f', struct.pack('<I', i))[0]


async def _axi4_slave_mem(dut, mem_dict):
    """Lightweight AXI4 slave memory responder.

    Handles single-beat AXI4 read/write transactions on the m_axi_* ports.
    Uses `mem_dict` (addr->bytes) as backing store addressed at 256-bit (32-byte)
    granularity.
    """
    clk = dut.m_axi_aclk

    # Default AXI4 slave ready/valid signals
    dut.m_axi_awready.value = 0
    dut.m_axi_wready.value = 0
    dut.m_axi_bvalid.value = 0
    dut.m_axi_bresp.value = 0
    dut.m_axi_arready.value = 0
    dut.m_axi_rvalid.value = 0
    dut.m_axi_rresp.value = 0
    dut.m_axi_rlast.value = 0
    dut.m_axi_rdata.value = 0

    while True:
        await RisingEdge(clk)

        # --- Write address channel ---
        aw_valid = int(dut.m_axi_awvalid.value)
        w_valid = int(dut.m_axi_wvalid.value)
        ar_valid = int(dut.m_axi_arvalid.value)

        # Handle write (accept AW + W in same cycle, respond with B next cycle)
        if aw_valid and w_valid:
            addr = int(dut.m_axi_awaddr.value)
            wdata = int(dut.m_axi_wdata.value)
            wstrb = int(dut.m_axi_wstrb.value)
            print(f"-> AXI MEM: writing addr {addr:#x} with {wstrb:#x}")

            # Accept both channels
            dut.m_axi_awready.value = 1
            dut.m_axi_wready.value = 1
            await RisingEdge(clk)
            dut.m_axi_awready.value = 0
            dut.m_axi_wready.value = 0

            # Apply write strobes to 256-bit (32-byte) memory
            existing = mem_dict.get(addr & ~0x1F, 0)
            for byte_i in range(32):
                if wstrb & (1 << byte_i):
                    byte_val = (wdata >> (byte_i * 8)) & 0xFF
                    # Clear and set the byte
                    existing &= ~(0xFF << (byte_i * 8))
                    existing |= byte_val << (byte_i * 8)
            mem_dict[addr & ~0x1F] = existing

            # Issue write response
            dut.m_axi_bvalid.value = 1
            dut.m_axi_bresp.value = 0  # OKAY
            await RisingEdge(clk)
            # Hold until bready
            while not int(dut.m_axi_bready.value):
                await RisingEdge(clk)
            dut.m_axi_bvalid.value = 0

        elif aw_valid and not w_valid:
            # Accept AW first, then wait for W
            addr = int(dut.m_axi_awaddr.value)
            print(f"-> AXI MEM: writing AW addr {addr:#x}")
            dut.m_axi_awready.value = 1
            await RisingEdge(clk)
            dut.m_axi_awready.value = 0
            # Wait for W
            while not int(dut.m_axi_wvalid.value):
                await RisingEdge(clk)
            wdata = int(dut.m_axi_wdata.value)
            wstrb = int(dut.m_axi_wstrb.value)
            print(f"-> AXI MEM: writing W data with {wstrb:#x}")
            dut.m_axi_wready.value = 1
            await RisingEdge(clk)
            dut.m_axi_wready.value = 0
            # Apply
            existing = mem_dict.get(addr & ~0x1F, 0)
            for byte_i in range(32):
                if wstrb & (1 << byte_i):
                    byte_val = (wdata >> (byte_i * 8)) & 0xFF
                    existing &= ~(0xFF << (byte_i * 8))
                    existing |= byte_val << (byte_i * 8)
            mem_dict[addr & ~0x1F] = existing
            dut.m_axi_bvalid.value = 1
            dut.m_axi_bresp.value = 0
            await RisingEdge(clk)
            while not int(dut.m_axi_bready.value):
                await RisingEdge(clk)
            dut.m_axi_bvalid.value = 0

        # Handle read (accept AR, respond with R)
        elif ar_valid:
            addr = int(dut.m_axi_araddr.value)
            dut.m_axi_arready.value = 1
            await RisingEdge(clk)
            dut.m_axi_arready.value = 0

            rdata = mem_dict.get(addr & ~0x1F, 0)
            dut.m_axi_rdata.value = rdata
            dut.m_axi_rvalid.value = 1; print(f"-> AXI MEM: reading addr {addr:#x} = {rdata}")
            dut.m_axi_rlast.value = 1
            dut.m_axi_rresp.value = 0  # OKAY
            await RisingEdge(clk)
            # Hold until rready
            while not int(dut.m_axi_rready.value):
                await RisingEdge(clk)
            dut.m_axi_rvalid.value = 0
            dut.m_axi_rlast.value = 0


class TpuRtlDriver:
    """RTL driver for the `tpu` DUT.

    AXI-Lite (write/read registers) is driven manually — this path is
    low-frequency (one write per command) so VPI overhead is negligible.

    AXI-Stream is driven via cocotbext-axi BFMs (P1.7-4):
      - axis_source (AXIStreamSource): drives s00_axis_* (DMA write path)
      - axis_sink   (AXIStreamSink):   monitors m00_axis_* (DMA read path)

    AXI4 Master (device memory LPDDR4 path):
      - _axi4_slave_mem coroutine simulates HP0 memory slave.
    """

    def __init__(self, dut):
        self.dut = dut
        self.clk = dut.s00_axi_aclk

        # Initialize AXI-Lite ports
        self.dut.s00_axi_awvalid.value = 0
        self.dut.s00_axi_wvalid.value = 0
        self.dut.s00_axi_bready.value = 0
        self.dut.s00_axi_arvalid.value = 0
        self.dut.s00_axi_rready.value = 0

        # AXI-Stream slave BFM (host → BRAM write path)
        self.axis_source = AxiStreamSource(
            AxiStreamBus.from_prefix(dut, "s00_axis"),
            dut.s00_axis_aclk,
            dut.s00_axis_aresetn,
            reset_active_level=False,
        )

        # AXI-Stream master BFM (BRAM → host read path)
        self.axis_sink = AxiStreamSink(
            AxiStreamBus.from_prefix(dut, "m00_axis"),
            dut.m00_axis_aclk,
            dut.m00_axis_aresetn,
            reset_active_level=False,
        )

        # Backing memory for AXI4 slave (simulates LPDDR4)
        self.axi_mem = {}

    async def reset(self):
        self.dut.s00_axi_aresetn.value = 0
        self.dut.s00_axis_aresetn.value = 0
        self.dut.m00_axis_aresetn.value = 0
        self.dut.m_axi_aresetn.value = 0
        await Timer(20, units="ns")
        self.dut.s00_axi_aresetn.value = 1
        self.dut.s00_axis_aresetn.value = 1
        self.dut.m00_axis_aresetn.value = 1
        self.dut.m_axi_aresetn.value = 1
        await RisingEdge(self.clk)
        # Start the AXI4 slave memory responder
        cocotb.start_soon(_axi4_slave_mem(self.dut, self.axi_mem))
        # Set ddr_phys_base = 0 for simulation (addresses map directly)
        await self.write_axi_lite(0x1C, 0)

    async def write_axi_lite(self, addr, data):
        self.dut.s00_axi_awaddr.value = addr
        self.dut.s00_axi_wdata.value = data
        self.dut.s00_axi_wstrb.value = 0xF
        self.dut.s00_axi_awvalid.value = 1
        self.dut.s00_axi_wvalid.value = 1
        self.dut.s00_axi_bready.value = 1

        aw_done = False
        w_done = False

        while not (aw_done and w_done):
            await ReadOnly()
            aw_ready = self.dut.s00_axi_awready.value
            w_ready = self.dut.s00_axi_wready.value
            await RisingEdge(self.clk)
            if not aw_done and aw_ready == 1:
                aw_done = True
                self.dut.s00_axi_awvalid.value = 0
            if not w_done and w_ready == 1:
                w_done = True
                self.dut.s00_axi_wvalid.value = 0

        while True:
            await ReadOnly()
            bvalid = self.dut.s00_axi_bvalid.value
            await RisingEdge(self.clk)
            if bvalid == 1:
                break
        self.dut.s00_axi_bready.value = 0

    async def read_axi_lite(self, addr):
        self.dut.s00_axi_araddr.value = addr
        self.dut.s00_axi_arvalid.value = 1
        self.dut.s00_axi_rready.value = 1

        while True:
            await ReadOnly()
            arready = self.dut.s00_axi_arready.value
            await RisingEdge(self.clk)
            if arready == 1:
                self.dut.s00_axi_arvalid.value = 0
                break

        while True:
            await ReadOnly()
            rvalid = self.dut.s00_axi_rvalid.value
            rdata = self.dut.s00_axi_rdata.value
            await RisingEdge(self.clk)
            if rvalid == 1:
                data = int(rdata)
                break
        self.dut.s00_axi_rready.value = 0
        return data

    async def wait_for_flag(self, offset, expected, timeout_cycles=1000):
        for _ in range(timeout_cycles):
            val = await self.read_axi_lite(offset)
            if val == expected:
                return
        raise TimeoutError(f"Timeout waiting for flag {expected} at offset {offset:#x}")

    async def write_bram(self, addr, values):
        """Write float32 array to device memory using AXIStreamSource BFM.

        Matches pynq_host.py: addr_devmem = addr // 8, length = values.size // 8
        (both in units of 256-bit beats).
        """
        values = np.asarray(values, dtype=np.float32).reshape(-1)
        # Pad to 256-bit boundary (8 x float32)
        pad_len = (8 - (values.size % 8)) % 8
        if pad_len > 0:
            values = np.pad(values, (0, pad_len), 'constant', constant_values=0)

        await self.wait_for_flag(0x04, 1)  # instr_ready
        await self.write_axi_lite(0x10, addr // 8)          # addr_devmem (beat-aligned)
        await self.write_axi_lite(0x18, values.size // 8)   # length (beat count)
        await self.write_axi_lite(0x00, 1 | 0x10)           # WRITE_DEVMEM | doorbell

        await self.wait_for_flag(0x08, 1)  # stream_ready

        # Pack float32 values into bytes and send as a single AXI-Stream frame.
        # The BFM handles TVALID/TREADY handshaking and TLAST automatically.
        frame_bytes = bytearray()
        for v in values:
            frame_bytes += struct.pack('<f', float(v))
        await self.axis_source.send(AxiStreamFrame(frame_bytes))

        await self.wait_for_flag(0x04, 1)  # instr_ready (done)

    async def devmem_to_l2(self, devmem_addr, l2_addr, length):
        """Copy length words from device memory to L2 (mode 5)."""
        await self.wait_for_flag(0x04, 1)
        await self.write_axi_lite(0x10, devmem_addr)
        await self.write_axi_lite(0x14, l2_addr)
        await self.write_axi_lite(0x18, length)
        await self.write_axi_lite(0x00, 5 | 0x10)  # DM_TO_L2 | doorbell
        await self.wait_for_flag(0x04, 1)

    async def l2_to_devmem(self, l2_addr, devmem_addr, length):
        """Copy length words from L2 to device memory (mode 6)."""
        await self.wait_for_flag(0x04, 1)
        await self.write_axi_lite(0x10, devmem_addr)
        await self.write_axi_lite(0x14, l2_addr)
        await self.write_axi_lite(0x18, length)
        await self.write_axi_lite(0x00, 6 | 0x10)  # L2_TO_DM | doorbell
        await self.wait_for_flag(0x04, 1)

    async def l2_to_l1(self, l2_addr, l1_base_addr, length):
        """Copy length words from L2 to compute tile L1 (mode 7)."""
        await self.wait_for_flag(0x04, 1)
        await self.write_axi_lite(0x0C, l1_base_addr)
        await self.write_axi_lite(0x14, l2_addr)
        await self.write_axi_lite(0x18, length)
        await self.write_axi_lite(0x00, 7 | 0x10)  # L2_TO_L1 | doorbell
        await self.wait_for_flag(0x04, 1)

    async def l1_to_l2(self, l1_base_addr, l2_addr, length):
        """Copy length words from compute tile L1 to L2 (mode 8)."""
        await self.wait_for_flag(0x04, 1)
        await self.write_axi_lite(0x0C, l1_base_addr)
        await self.write_axi_lite(0x14, l2_addr)
        await self.write_axi_lite(0x18, length)
        await self.write_axi_lite(0x00, 8 | 0x10)  # L1_TO_L2 | doorbell
        await self.wait_for_flag(0x04, 1)

    async def read_bram(self, addr, length):
        """Read float32 array from device memory using AXIStreamSink BFM.

        Matches pynq_host.py: addr_devmem = addr // 8, length in beats.
        """
        beat_length = (length + 7) // 8

        await self.wait_for_flag(0x04, 1)  # instr_ready
        await self.write_axi_lite(0x10, addr // 8)     # addr_devmem (beat-aligned)
        await self.write_axi_lite(0x18, beat_length)   # length (beat count)
        await self.write_axi_lite(0x00, 2 | 0x10)      # READ_DEVMEM | doorbell

        # The BFM keeps TREADY asserted and accumulates incoming beats into a
        # frame.  recv() returns when TLAST is seen.
        frame = await self.axis_sink.recv()

        await self.wait_for_flag(0x04, 1)  # instr_ready (done)

        # Unpack received bytes back to float32 list, trim to requested length
        raw = bytes(frame.tdata)
        n_words = len(raw) // 4
        result = [int_to_float(struct.unpack_from('<I', raw, i * 4)[0])
                  for i in range(min(n_words, length))]
        return result


@cocotb.test()
async def test_data_integrity(dut):
    cocotb.start_soon(Clock(dut.s00_axi_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.s00_axis_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.m00_axis_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.m_axi_aclk, 10, units="ns").start())

    driver = TpuRtlDriver(dut)
    await driver.reset()

    sizes = [16]
    for size in sizes:
        pattern = np.arange(size, dtype=np.float32)
        await driver.write_bram(0, pattern)
        result = await driver.read_bram(0, size)

        assert abs(result[0]) < 1e-6, \
            f"First element {result[0]} != 0.0. Full start: {result[:8]}"
        for i in range(size):
            assert abs(result[i] - pattern[i]) < 1e-6, \
                f"Mismatch at index {i}: expected {pattern[i]}, got {result[i]}"

    # Known values
    pattern = np.array([1.0, -1.0, 0.5, -0.5, 2.0, 4.0, 8.0, 16.0], dtype=np.float32)
    await driver.write_bram(0, pattern)
    result = await driver.read_bram(0, len(pattern))
    for i in range(len(pattern)):
        assert abs(result[i] - pattern[i]) < 1e-6, f"Mismatch at index {i}"

    dut._log.info("ALL TESTS PASSED")


@cocotb.test()
async def test_boundary_n8(dut):
    """N=8 = FIFO depth. Tests drain from full FIFO. Catches Bug A (first element loss)
    and Bug B (last FIFO word duplicated on drain boundary)."""
    cocotb.start_soon(Clock(dut.s00_axi_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.s00_axis_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.m00_axis_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.m_axi_aclk, 10, units="ns").start())

    driver = TpuRtlDriver(dut)
    await driver.reset()

    N = 8
    pattern = np.arange(N, dtype=np.float32)
    await driver.write_bram(0, pattern)
    result = await driver.read_bram(0, N)

    assert abs(result[0] - 0.0) < 1e-6, \
        f"Bug A: first element {result[0]} != 0.0. Result: {result}"
    for i in range(N - 1):
        assert result[i] != result[i + 1], \
            f"Bug B: duplicate at index {i}/{i+1}: {result[i]}"
    for i in range(N):
        assert abs(result[i] - float(i)) < 1e-6, \
            f"Mismatch at index {i}: expected {float(i)}, got {result[i]}"

    dut._log.info("test_boundary_n8 PASSED")


@cocotb.test()
async def test_boundary_n9(dut):
    """N=9 = FIFO depth + 1. Tests prefill-to-steady-state transition where Bug B
    duplicates word 7 (the last prefill word that drains before steady-state kicks in)."""
    cocotb.start_soon(Clock(dut.s00_axi_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.s00_axis_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.m00_axis_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.m_axi_aclk, 10, units="ns").start())
    driver = TpuRtlDriver(dut)
    await driver.reset()

    N = 9
    pattern = np.arange(N, dtype=np.float32)
    await driver.write_bram(0, pattern)
    result = await driver.read_bram(0, N)

    assert abs(result[0] - 0.0) < 1e-6, \
        f"Bug A: first element {result[0]} != 0.0. Result: {result}"
    for i in range(N - 1):
        assert result[i] != result[i + 1], \
            f"Bug B: duplicate at index {i}/{i+1}: {result[i]}"
    for i in range(N):
        assert abs(result[i] - float(i)) < 1e-6, \
            f"Mismatch at index {i}: expected {float(i)}, got {result[i]}"

    dut._log.info("test_boundary_n9 PASSED")


@cocotb.test()
async def test_boundary_n16(dut):
    """N=16. Explicit Bug A/B assertions on the same size used by test_data_integrity."""
    cocotb.start_soon(Clock(dut.s00_axi_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.s00_axis_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.m00_axis_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.m_axi_aclk, 10, units="ns").start())

    driver = TpuRtlDriver(dut)
    await driver.reset()

    N = 16
    pattern = np.arange(N, dtype=np.float32)
    await driver.write_bram(0, pattern)
    result = await driver.read_bram(0, N)

    assert abs(result[0] - 0.0) < 1e-6, \
        f"Bug A: first element {result[0]} != 0.0. Result: {result}"
    for i in range(N - 1):
        assert result[i] != result[i + 1], \
            f"Bug B: duplicate at index {i}/{i+1}: {result[i]}"
    for i in range(N):
        assert abs(result[i] - float(i)) < 1e-6, \
            f"Mismatch at index {i}: expected {float(i)}, got {result[i]}"

    dut._log.info("test_boundary_n16 PASSED")
