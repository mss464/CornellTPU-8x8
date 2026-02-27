"""
PYNQ Host Interface for Mini-TPU

Hardware abstraction layer for interacting with the Mini-TPU on PYNQ boards.

Register map (AXI-Lite offsets):
  0x00  tpu_mode    — [3:0] mode, [4] doorbell (P1.8: write mode|0x10 to trigger)
  0x04  instr_ready — 1 when all sub-FSMs idle (dma_engine + compute_ctrl + l2_ctrl)
  0x08  stream_ready— 1 when DMA stream path open
  0x0C  addr_ram    — IRAM base address (mode 4)
  0x10  addr_devmem — device memory base address (modes 1/2)
  0x14  addr_l2     — L2 SRAM base address (modes 5–8)
  0x18  length      — transfer length in words

Modes:
  1 = WRITE_DEVMEM  — host → device memory (AXI-Stream DMA)
  2 = READ_DEVMEM   — device memory → host (AXI-Stream DMA)
  3 = COMPUTE       — execute IRAM kernel
  4 = WRITE_IRAM    — host → instruction RAM (AXI-Stream DMA)
  5 = DM_TO_L2      — device memory → L2 block copy
  6 = L2_TO_DM      — L2 → device memory block copy
  7 = L2_TO_L1      — L2 → compute tile L1 block copy
  8 = L1_TO_L2      — compute tile L1 → L2 block copy

Doorbell protocol (P1.8):
  Write (mode | 0x10) to 0x00. Hardware latches mode, clears doorbell,
  dispatches to the appropriate sub-FSM. Hardware sets instr_ready=1
  (and stream_ready=1 for DMA modes) when done. No trailing IDLE write needed.

Concurrent execution (P2.08):
  dma_engine (modes 1/2/4/5/6) and compute_ctrl (mode 3) use disjoint BRAM
  ports and can run simultaneously. l2_ctrl (modes 7/8) also runs independently.
  instr_ready=1 only when ALL three sub-FSMs are idle.
"""

import time
import os
import json
import struct
import numpy as np

try:
    from pynq import Overlay, allocate
except ImportError:
    Overlay = None
    allocate = None

# AXI-Lite register offsets
REG_ADDR = {
    "tpu_mode":     0x00,
    "instr_ready":  0x04,
    "stream_ready": 0x08,
    "addr_ram":     0x0C,
    "addr_devmem":  0x10,
    "addr_l2":      0x14,
    "length":       0x18,
}

DOORBELL_BIT = 0x10  # bit 4 of tpu_mode register

# Mode constants
class TpuMode:
    IDLE       = 0
    WRITE_BRAM = 1   # alias: WRITE_DEVMEM
    READ_BRAM  = 2   # alias: READ_DEVMEM
    COMPUTE    = 3
    WRITE_IRAM = 4
    DM_TO_L2   = 5
    L2_TO_DM   = 6
    L2_TO_L1   = 7
    L1_TO_L2   = 8


class TpuDriver:
    """Driver for Mini-TPU hardware on PYNQ-based FPGA boards.

    Uses the P1.8 doorbell protocol: all operations write (mode | 0x10) to
    tpu_mode in a single MMIO write, which atomically arms the mode and asserts
    the doorbell. No trailing IDLE write is needed or sent.
    """

    def __init__(self, bitstream=None, tpu_name=None, dma_name=None, program=False):
        if Overlay is None:
            raise RuntimeError("pynq library not available — must run on PYNQ board")

        config = {
            "bitstream": "minitpu.bit",
            "handoff":   "minitpu.hwh",
            "tpu_names": ["tpu_0", "tpu_top_0", "tpu"],
            "dma_names": ["axi_dma_0", "axi_dma", "dma"],
        }
        for p in ["hw_config.json", "tpu/hw_config.json",
                  "../tpu/hw_config.json", "/home/xilinx/tpu_deploy/hw_config.json"]:
            if os.path.exists(p):
                with open(p) as f:
                    try:
                        config.update(json.load(f))
                    except json.JSONDecodeError:
                        pass
                break

        if bitstream is None:
            bitstream = config["bitstream"]
            for prefix in ["", "tpu/", "/home/xilinx/tpu_deploy/"]:
                candidate = prefix + bitstream
                if os.path.exists(candidate):
                    bitstream = candidate
                    break

        hwh_path = os.path.splitext(bitstream)[0] + ".hwh"
        if not os.path.exists(hwh_path):
            alt_hwh = os.path.join(os.path.dirname(bitstream), config["handoff"])
            if os.path.exists(alt_hwh):
                try:
                    os.rename(alt_hwh, hwh_path)
                except OSError:
                    pass

        self.overlay = Overlay(bitstream, download=program)
        if program:
            print(f"FPGA programmed with {bitstream}")

        if dma_name is None:
            for name in config["dma_names"]:
                if hasattr(self.overlay, name):
                    dma_name = name
                    break
        if tpu_name is None:
            for name in config["tpu_names"]:
                if hasattr(self.overlay, name):
                    tpu_name = name
                    break

        if dma_name is None or not hasattr(self.overlay, dma_name):
            raise RuntimeError(f"DMA not found. Available: {list(self.overlay.ip_dict.keys())}")
        if tpu_name is None or not hasattr(self.overlay, tpu_name):
            raise RuntimeError(f"TPU not found. Available: {list(self.overlay.ip_dict.keys())}")

        self.dma  = getattr(self.overlay, dma_name)
        self.ctrl = getattr(self.overlay, tpu_name)
        self.mmio = self.ctrl.mmio
        print(f"TPU HW ready (DMA={dma_name}, TPU={tpu_name})")

    # -------------------------------------------------------------------------
    # Low-level helpers
    # -------------------------------------------------------------------------
    def _doorbell(self, mode):
        """Write (mode | DOORBELL_BIT) to trigger sub-FSM dispatch (P1.8)."""
        self.mmio.write(REG_ADDR["tpu_mode"], mode | DOORBELL_BIT)

    def wait_for_flag(self, name, expected=1, poll_delay=0.001, timeout=10.0):
        """Poll a status register until it equals `expected`."""
        offset = REG_ADDR[name]
        deadline = time.time() + timeout
        while self.mmio.read(offset) != expected:
            if time.time() > deadline:
                regs = {k: hex(self.mmio.read(v)) for k, v in REG_ADDR.items()}
                raise TimeoutError(f"Timeout waiting for {name}={expected}. Regs: {regs}")
            time.sleep(poll_delay)

    # -------------------------------------------------------------------------
    # Host ↔ Device Memory (modes 1 / 2)
    # -------------------------------------------------------------------------
    def write_bram(self, addr, values):
        """Write float32 array to device memory at `addr` (mode WRITE_DEVMEM=1).

        Doorbell triggers dma_engine. Waits for stream_ready before DMA transfer.
        """
        values = np.asarray(values, dtype=np.float32).reshape(-1)
        buf = allocate(shape=values.shape, dtype=np.float32)
        try:
            self.wait_for_flag("instr_ready")
            self.mmio.write(REG_ADDR["addr_devmem"], addr)
            self.mmio.write(REG_ADDR["length"], values.size)
            self._doorbell(TpuMode.WRITE_BRAM)
            self.wait_for_flag("stream_ready")
            buf[:] = values
            self.dma.sendchannel.transfer(buf)
            self.dma.sendchannel.wait()
            self.wait_for_flag("instr_ready")
        finally:
            buf.freebuffer()

    def read_bram(self, addr, length):
        """Read `length` float32 words from device memory at `addr` (mode READ_DEVMEM=2).

        DMA recv channel armed before doorbell to avoid missing first beats.
        """
        buf = allocate(shape=(length,), dtype=np.float32)
        try:
            self.wait_for_flag("instr_ready")
            self.mmio.write(REG_ADDR["addr_devmem"], addr)
            self.mmio.write(REG_ADDR["length"], length)
            self.dma.recvchannel.transfer(buf)   # arm DMA before TPU starts streaming
            self._doorbell(TpuMode.READ_BRAM)
            self.dma.recvchannel.wait()
            self.wait_for_flag("instr_ready")
            return np.copy(buf)
        finally:
            buf.freebuffer()

    # -------------------------------------------------------------------------
    # Instruction RAM (mode 4)
    # -------------------------------------------------------------------------
    def write_instructions(self, instructions, base_addr=1):
        """Write 64-bit instructions to IRAM (mode WRITE_IRAM=4).

        base_addr=1 is the required workaround for the BRAM iram_addr timing:
        the BRAM captures iram_addr at the same posedge as the write, so the
        pre-NBA address is addr_ram + (write_pointer>>1) - 1. Setting addr_ram=1
        means instruction 0 lands at IRAM[0] correctly.
        See docs/verification.md §Known Issues §1 for full analysis.
        """
        instructions = np.asarray(instructions, dtype=np.uint64)
        buf = allocate(shape=instructions.shape, dtype=np.uint64)
        try:
            self.wait_for_flag("instr_ready")
            self.mmio.write(REG_ADDR["addr_ram"], base_addr)
            self.mmio.write(REG_ADDR["length"], 2 * len(instructions))
            self._doorbell(TpuMode.WRITE_IRAM)
            self.wait_for_flag("stream_ready")
            buf[:] = instructions
            self.dma.sendchannel.transfer(buf)
            self.dma.sendchannel.wait()
            self.wait_for_flag("instr_ready")
        finally:
            buf.freebuffer()

    # -------------------------------------------------------------------------
    # Compute (mode 3)
    # -------------------------------------------------------------------------
    def compute(self, timeout=30.0):
        """Execute the IRAM kernel on the compute tile (mode COMPUTE=3).

        With P2.08 concurrent arbiter, this can overlap with DMA operations.
        Waits for instr_ready=1 (all sub-FSMs idle) before and after.
        """
        self.wait_for_flag("instr_ready", timeout=timeout)
        self.mmio.write(REG_ADDR["length"], 0)
        self._doorbell(TpuMode.COMPUTE)
        self.wait_for_flag("instr_ready", timeout=timeout)

    # -------------------------------------------------------------------------
    # DevMem ↔ L2 (modes 5 / 6)
    # -------------------------------------------------------------------------
    def devmem_to_l2(self, devmem_addr, l2_addr, length):
        """Block-copy `length` words from device memory to L2 (mode DM_TO_L2=5)."""
        self.wait_for_flag("instr_ready")
        self.mmio.write(REG_ADDR["addr_devmem"], devmem_addr)
        self.mmio.write(REG_ADDR["addr_l2"],     l2_addr)
        self.mmio.write(REG_ADDR["length"],      length)
        self._doorbell(TpuMode.DM_TO_L2)
        self.wait_for_flag("instr_ready")

    def l2_to_devmem(self, l2_addr, devmem_addr, length):
        """Block-copy `length` words from L2 to device memory (mode L2_TO_DM=6)."""
        self.wait_for_flag("instr_ready")
        self.mmio.write(REG_ADDR["addr_devmem"], devmem_addr)
        self.mmio.write(REG_ADDR["addr_l2"],     l2_addr)
        self.mmio.write(REG_ADDR["length"],      length)
        self._doorbell(TpuMode.L2_TO_DM)
        self.wait_for_flag("instr_ready")

    # -------------------------------------------------------------------------
    # L2 ↔ L1 (modes 7 / 8)
    # -------------------------------------------------------------------------
    def l2_to_l1(self, l2_addr, l1_base_addr, length):
        """Block-copy `length` words from L2 to compute tile L1 (mode L2_TO_L1=7)."""
        self.wait_for_flag("instr_ready")
        self.mmio.write(REG_ADDR["addr_ram"],    l1_base_addr)
        self.mmio.write(REG_ADDR["addr_l2"],     l2_addr)
        self.mmio.write(REG_ADDR["length"],      length)
        self._doorbell(TpuMode.L2_TO_L1)
        self.wait_for_flag("instr_ready")

    def l1_to_l2(self, l1_base_addr, l2_addr, length):
        """Block-copy `length` words from compute tile L1 to L2 (mode L1_TO_L2=8)."""
        self.wait_for_flag("instr_ready")
        self.mmio.write(REG_ADDR["addr_ram"],    l1_base_addr)
        self.mmio.write(REG_ADDR["addr_l2"],     l2_addr)
        self.mmio.write(REG_ADDR["length"],      length)
        self._doorbell(TpuMode.L1_TO_L2)
        self.wait_for_flag("instr_ready")


def load_instructions(filepath):
    """Load hex instruction file (one 64-bit instruction per line) → uint64 array."""
    instructions = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                instructions.append(int(line, 16))
    return np.array(instructions, dtype=np.uint64)
