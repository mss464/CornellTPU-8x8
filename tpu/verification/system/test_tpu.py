import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer, ReadOnly
import struct
import numpy as np

def float_to_int(f):
    return struct.unpack('<I', struct.pack('<f', f))[0]

def int_to_float(i):
    return struct.unpack('<f', struct.pack('<I', i))[0]

class TpuRtlDriver:
    def __init__(self, dut):
        self.dut = dut
        self.clk = dut.s00_axi_aclk
        self.rstn = dut.s00_axi_aresetn
        
        # Initialize AXI Lite
        self.dut.s00_axi_awvalid.value = 0
        self.dut.s00_axi_wvalid.value = 0
        self.dut.s00_axi_bready.value = 0
        self.dut.s00_axi_arvalid.value = 0
        self.dut.s00_axi_rready.value = 0
        
        # Initialize AXI Stream (Slave)
        self.dut.s00_axis_tvalid.value = 0
        self.dut.s00_axis_tlast.value = 0
        
        # Initialize AXI Stream (Master)
        self.dut.m00_axis_tready.value = 0

    async def reset(self):
        self.rstn.value = 0
        self.dut.s00_axis_aresetn.value = 0
        self.dut.m00_axis_aresetn.value = 0
        await Timer(20, units="ns")
        self.rstn.value = 1
        self.dut.s00_axis_aresetn.value = 1
        self.dut.m00_axis_aresetn.value = 1
        await RisingEdge(self.clk)

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
        raise TimeoutError(f"Timeout waiting for flag {expected} at offset {offset}")

    async def write_bram(self, addr, values):
        await self.wait_for_flag(0x04, 1) # instr_ready
        await self.write_axi_lite(0x10, addr)  # addr_devmem (slv_reg4)
        await self.write_axi_lite(0x18, len(values))
        await self.write_axi_lite(0x00, 1) # WRITE_DEVMEM
        
        await self.wait_for_flag(0x08, 1) # stream_ready
        
        # Send AXI Stream Data
        for i, val in enumerate(values):
            self.dut.s00_axis_tdata.value = float_to_int(val)
            self.dut.s00_axis_tstrb.value = 0xF
            self.dut.s00_axis_tlast.value = 1 if i == len(values)-1 else 0
            self.dut.s00_axis_tvalid.value = 1
            
            while True:
                await ReadOnly()
                tready = self.dut.s00_axis_tready.value
                await RisingEdge(self.clk)
                if tready == 1:
                    break
        self.dut.s00_axis_tvalid.value = 0
        self.dut.s00_axis_tlast.value = 0
        
        await self.wait_for_flag(0x04, 1) # instr_ready
        await self.write_axi_lite(0x00, 0) # IDLE

    async def devmem_to_l2(self, devmem_addr, l2_addr, length):
        """Copy length words from device memory to L2 (mode 5)."""
        await self.wait_for_flag(0x04, 1)
        await self.write_axi_lite(0x10, devmem_addr)  # addr_devmem
        await self.write_axi_lite(0x14, l2_addr)      # addr_l2
        await self.write_axi_lite(0x18, length)
        await self.write_axi_lite(0x00, 5)             # DM_TO_L2
        await self.wait_for_flag(0x04, 1)
        await self.write_axi_lite(0x00, 0)             # IDLE

    async def l2_to_devmem(self, l2_addr, devmem_addr, length):
        """Copy length words from L2 to device memory (mode 6)."""
        await self.wait_for_flag(0x04, 1)
        await self.write_axi_lite(0x10, devmem_addr)  # addr_devmem
        await self.write_axi_lite(0x14, l2_addr)      # addr_l2
        await self.write_axi_lite(0x18, length)
        await self.write_axi_lite(0x00, 6)             # L2_TO_DM
        await self.wait_for_flag(0x04, 1)
        await self.write_axi_lite(0x00, 0)             # IDLE

    async def l2_to_l1(self, l2_addr, l1_base_addr, length):
        """Copy length words from L2 to compute tile L1 (mode 7)."""
        await self.wait_for_flag(0x04, 1)
        await self.write_axi_lite(0x0C, l1_base_addr) # addr_ram (L1 base)
        await self.write_axi_lite(0x14, l2_addr)      # addr_l2
        await self.write_axi_lite(0x18, length)
        await self.write_axi_lite(0x00, 7)             # L2_TO_L1
        await self.wait_for_flag(0x04, 1)
        await self.write_axi_lite(0x00, 0)             # IDLE

    async def l1_to_l2(self, l1_base_addr, l2_addr, length):
        """Copy length words from compute tile L1 to L2 (mode 8)."""
        await self.wait_for_flag(0x04, 1)
        await self.write_axi_lite(0x0C, l1_base_addr) # addr_ram (L1 base)
        await self.write_axi_lite(0x14, l2_addr)      # addr_l2
        await self.write_axi_lite(0x18, length)
        await self.write_axi_lite(0x00, 8)             # L1_TO_L2
        await self.wait_for_flag(0x04, 1)
        await self.write_axi_lite(0x00, 0)             # IDLE

    async def read_bram(self, addr, length):
        await self.wait_for_flag(0x04, 1) # instr_ready
        await self.write_axi_lite(0x10, addr)  # addr_devmem (slv_reg4)
        await self.write_axi_lite(0x18, length)
        await self.write_axi_lite(0x00, 2) # READ_DEVMEM
        
        out_values = []
        self.dut.m00_axis_tready.value = 1
        
        while len(out_values) < length:
            await ReadOnly()
            tvalid = self.dut.m00_axis_tvalid.value
            tdata = self.dut.m00_axis_tdata.value
            await RisingEdge(self.clk)
            if tvalid == 1:
                val = int(tdata)
                out_values.append(int_to_float(val))
        
        self.dut.m00_axis_tready.value = 0
        
        await self.wait_for_flag(0x04, 1) # instr_ready
        await self.write_axi_lite(0x00, 0) # IDLE
        return out_values

@cocotb.test()
async def test_data_integrity(dut):
    # Start clocks
    cocotb.start_soon(Clock(dut.s00_axi_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.s00_axis_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.m00_axis_aclk, 10, units="ns").start())
    
    driver = TpuRtlDriver(dut)
    await driver.reset()
    
    sizes = [16]
    for size in sizes:
        pattern = np.arange(size, dtype=np.float32)
        await driver.write_bram(0, pattern)
        result = await driver.read_bram(0, size)
        
        assert abs(result[0]) < 1e-6, f"First element {result[0]} != 0.0. Full start: {result[:8]}"
        for i in range(size):
            assert abs(result[i] - pattern[i]) < 1e-6, f"Mismatch at index {i}: expected {pattern[i]}, got {result[i]}"
            
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
