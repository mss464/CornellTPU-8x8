"""
test_tpu_compute.py — System-level verification of TPU mode 3 (COMPUTE).

Tests the full compute path: host → devmem → L2 → L1 → [kernel] → L1 → L2 → devmem → host.

IRAM write note (mode 4 addr_ram=1 workaround):
  The tpu.sv iram_addr counter updates at the same posedge as the BRAM write.
  The BRAM model captures addra using the pre-NBA value of iram_addr.
  This causes an off-by-one: instruction N is written to the address established
  by the PREVIOUS odd write-pointer update, not the current one.

  Workaround: set addr_ram=1 (not 0) when loading N instructions starting at IRAM[0].
  This makes the pre-NBA address sequence produce: addr 0, 1, 2, ..., N-1 correctly.
  See tpu/docs/verification.md §Known Issues §2 for full analysis.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly
import struct
import numpy as np

from test_tpu import TpuRtlDriver, float_to_int, int_to_float


def start_clocks(dut):
    cocotb.start_soon(Clock(dut.s00_axi_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.s00_axis_aclk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.m00_axis_aclk, 10, units="ns").start())


class TpuComputeDriver(TpuRtlDriver):
    """Extends TpuRtlDriver with IRAM write and COMPUTE execute methods."""

    async def write_iram(self, instructions):
        """Write 64-bit instructions to IRAM via mode 4 (WRITE_IRAM).

        Instructions are sent as pairs of 32-bit AXI-Stream words:
          word 2i+0: instr[31:0]  (lower half)
          word 2i+1: instr[63:32] (upper half)

        Uses addr_ram=1 to work around the iram_addr off-by-one timing issue.
        Loads instructions at IRAM addresses 0, 1, 2, ... correctly.

        See module docstring for full analysis.
        """
        num_words = len(instructions) * 2

        await self.wait_for_flag(0x04, 1)  # instr_ready
        # addr_ram=1 is the workaround: pre-advances iram_addr so the BRAM
        # write posedge sees the correct (pre-NBA) address for each instruction.
        await self.write_axi_lite(0x0C, 1)         # addr_ram = 1 (workaround)
        await self.write_axi_lite(0x18, num_words)  # length in 32-bit words
        await self.write_axi_lite(0x00, 4)          # WRITE_IRAM

        await self.wait_for_flag(0x08, 1)  # stream_ready

        # Flatten instructions into 32-bit word pairs (lower then upper)
        words = []
        for instr in instructions:
            words.append(int(instr) & 0xFFFFFFFF)
            words.append((int(instr) >> 32) & 0xFFFFFFFF)

        for i, w in enumerate(words):
            self.dut.s00_axis_tdata.value = w
            self.dut.s00_axis_tstrb.value = 0xF
            self.dut.s00_axis_tlast.value = 1 if i == len(words) - 1 else 0
            self.dut.s00_axis_tvalid.value = 1

            while True:
                await ReadOnly()
                tready = self.dut.s00_axis_tready.value
                await RisingEdge(self.clk)
                if tready == 1:
                    break
        self.dut.s00_axis_tvalid.value = 0
        self.dut.s00_axis_tlast.value = 0

        await self.wait_for_flag(0x04, 1)  # instr_ready
        await self.write_axi_lite(0x00, 0)  # IDLE

    async def execute(self, timeout_cycles=5000):
        """Execute compute mode (mode 3). Waits for kernel completion."""
        await self.wait_for_flag(0x04, 1)
        await self.write_axi_lite(0x18, 0)  # dma_len=0 (unused for COMPUTE)
        await self.write_axi_lite(0x00, 3)  # COMPUTE
        await self.wait_for_flag(0x04, 1, timeout_cycles=timeout_cycles)
        await self.write_axi_lite(0x00, 0)  # IDLE


def encode_vpu_instr(addr_a=0, addr_b=0, addr_out=0, vpu_type=0,
                     vreg_dst=0, vreg_a=0, vreg_b=0, vpu_opcode=0, scalar_b=0):
    """Encode a VPU instruction (mode=0) using decoder.sv hardware field layout.

    Decoder field map:
      [63:62] = mode (0=VPU, 1=systolic, 3=HALT)
      [61:49] = addr_a (13-bit)
      [48:36] = addr_b (13-bit)
      [35:23] = addr_out (13-bit)
      [22:20] = vpu_type (1=VLOAD, 2=VSTORE, 3=VCOMPUTE)
      [19:17] = vreg_dst
      [16:14] = vreg_a
      [13:11] = vreg_b
      [6:4]   = vpu_opcode
      [3]     = scalar_b
    """
    instr = 0
    instr |= (0 & 0x3) << 62                 # mode=0 (VPU)
    instr |= (addr_a  & 0x1FFF) << 49
    instr |= (addr_b  & 0x1FFF) << 36
    instr |= (addr_out & 0x1FFF) << 23
    instr |= (vpu_type & 0x7) << 20
    instr |= (vreg_dst & 0x7) << 17
    instr |= (vreg_a   & 0x7) << 14
    instr |= (vreg_b   & 0x7) << 11
    instr |= (vpu_opcode & 0x7) << 4
    instr |= (scalar_b & 0x1) << 3
    return instr


HALT_INSTR = 3 << 62  # mode=3


# ---------------------------------------------------------------------------
# Test 1: Identity kernel — VLOAD V0 then VSTORE V0
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_compute_identity_kernel(dut):
    """End-to-end COMPUTE mode test with identity kernel (vload + vstore).

    Data flow:
      Host → DevMem[0:8]  (mode 1)
      DevMem[0:8] → L2[0:8]  (mode 5)
      L2[0:8] → L1[0:8]   (mode 7)
      IRAM ← [vload(V0,0), vstore(V0,8), halt]  (mode 4)
      COMPUTE: V0=L1[0:7], L1[8:15]=V0  (mode 3)
      L1[8:15] → L2[8:15]  (mode 8)
      L2[8:15] → DevMem[8:15]  (mode 6)
      Host ← DevMem[8:15]  (mode 2)
      Verify output == input
    """
    start_clocks(dut)
    driver = TpuComputeDriver(dut)
    await driver.reset()

    # Input: 8 known float values
    n = 8
    input_data = np.array([float(i + 1) for i in range(n)], dtype=np.float32)

    # Stage 1: Host → DevMem[0]
    await driver.write_bram(0, input_data)

    # Stage 2: DevMem[0:8] → L2[0:8]
    await driver.devmem_to_l2(devmem_addr=0, l2_addr=0, length=n)

    # Stage 3: L2[0:8] → L1[0:8]
    await driver.l2_to_l1(l2_addr=0, l1_base_addr=0, length=n)

    # Stage 4: Write identity kernel to IRAM
    #   vload(V0, addr=0):  read L1[0:7] into V0
    #   vstore(V0, addr=8): write V0 to L1[8:15]
    #   halt
    vload  = encode_vpu_instr(addr_a=0,  vpu_type=1, vreg_dst=0)
    vstore = encode_vpu_instr(addr_out=8, vpu_type=2, vreg_a=0)
    await driver.write_iram([vload, vstore, HALT_INSTR])

    # Stage 5: Execute kernel
    await driver.execute(timeout_cycles=5000)

    # Stage 6: L1[8:15] → L2[8:15]
    await driver.l1_to_l2(l1_base_addr=8, l2_addr=8, length=n)

    # Stage 7: L2[8:15] → DevMem[8:15]
    await driver.l2_to_devmem(l2_addr=8, devmem_addr=8, length=n)

    # Stage 8: Host ← DevMem[8:15]
    result = await driver.read_bram(8, n)

    # Verify identity
    for i in range(n):
        assert abs(result[i] - input_data[i]) < 1e-6, \
            f"Identity mismatch at [output[{i}]]: expected {input_data[i]}, got {result[i]}"

    dut._log.info("test_compute_identity_kernel PASSED")


# ---------------------------------------------------------------------------
# Test 2: VADD kernel — V2 = V0 + V1
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_compute_vadd_kernel(dut):
    """COMPUTE mode VADD test: stage A and B into L1, compute C = A+B.

    Kernel: vload(V0, addr=0), vload(V1, addr=8), vadd(V2,V0,V1), vstore(V2, addr=16)
    A at L1[0:7], B at L1[8:15], output C at L1[16:23].
    """
    start_clocks(dut)
    driver = TpuComputeDriver(dut)
    await driver.reset()

    n = 8
    a_data = np.array([float(i + 1) for i in range(n)],     dtype=np.float32)  # [1..8]
    b_data = np.array([float(i * 2 + 10) for i in range(n)], dtype=np.float32)  # [10,12,..24]
    expected = a_data + b_data

    # Stage A into DevMem[0:8], then L2→L1[0:8]
    await driver.write_bram(0, a_data)
    await driver.devmem_to_l2(devmem_addr=0, l2_addr=0, length=n)
    await driver.l2_to_l1(l2_addr=0, l1_base_addr=0, length=n)

    # Stage B into DevMem[8:15], then L2→L1[8:15]
    await driver.write_bram(8, b_data)
    await driver.devmem_to_l2(devmem_addr=8, l2_addr=8, length=n)
    await driver.l2_to_l1(l2_addr=8, l1_base_addr=8, length=n)

    # Build VADD kernel
    #   vload  V0, addr=0   : load A from L1[0:7]
    #   vload  V1, addr=8   : load B from L1[8:15]
    #   vcompute V2=V0+V1   : vadd, opcode=0
    #   vstore V2, addr=16  : store result to L1[16:23]
    #   halt
    vload0   = encode_vpu_instr(addr_a=0,   vpu_type=1, vreg_dst=0)
    vload1   = encode_vpu_instr(addr_a=8,   vpu_type=1, vreg_dst=1)
    vadd     = encode_vpu_instr(vpu_type=3, vreg_dst=2, vreg_a=0, vreg_b=1, vpu_opcode=0)
    vstore2  = encode_vpu_instr(addr_out=16, vpu_type=2, vreg_a=2)
    await driver.write_iram([vload0, vload1, vadd, vstore2, HALT_INSTR])

    # Execute
    await driver.execute(timeout_cycles=10000)

    # Read result: L1[16:23] → L2[16:23] → DevMem[16:23] → host
    await driver.l1_to_l2(l1_base_addr=16, l2_addr=16, length=n)
    await driver.l2_to_devmem(l2_addr=16, devmem_addr=16, length=n)
    result = await driver.read_bram(16, n)

    for i in range(n):
        assert abs(result[i] - expected[i]) < 1e-4, \
            f"VADD mismatch at [C[{i}]]: expected {expected[i]}, got {result[i]}"

    dut._log.info("test_compute_vadd_kernel PASSED")
