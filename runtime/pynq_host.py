"""
PYNQ Host Interface for Mini-TPU
"""

import time
import os
import json
import struct
import threading
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

DMA_TRANSFER_TIMEOUT = 8.0  # seconds before a DMA wait is considered hung


def _dma_wait(channel, timeout=DMA_TRANSFER_TIMEOUT):
    """Wait for a PYNQ DMA channel with a timeout.

    PYNQ's channel.wait() has no built-in timeout; a hung FPGA (e.g. TLAST
    never asserted) would block indefinitely.  This helper runs wait() in a
    daemon thread and raises TimeoutError if it doesn't finish in time.
    """
    result = [None]
    exc_holder = [None]

    def _do_wait():
        try:
            channel.wait()
        except Exception as e:  # noqa: BLE001
            exc_holder[0] = e
        finally:
            result[0] = True

    t = threading.Thread(target=_do_wait, daemon=True)
    t.start()
    t.join(timeout)
    if not result[0]:
        raise TimeoutError(
            f"DMA transfer timed out after {timeout}s "
            "— FPGA may not have completed the transfer (check TLAST)"
        )
    if exc_holder[0]:
        raise exc_holder[0]

# Mode constants
class TpuMode:
    IDLE       = 0
    WRITE_BRAM = 1
    READ_BRAM  = 2
    COMPUTE    = 3
    WRITE_IRAM = 4
    DM_TO_L2   = 5
    L2_TO_DM   = 6
    L2_TO_L1   = 7
    L1_TO_L2   = 8

class TpuDriver:
    def __init__(self, bitstream=None, tpu_name=None, dma_name=None, program=False):
        if Overlay is None:
            raise RuntimeError("pynq library not available")

        self.overlay = Overlay(bitstream or "minitpu.bit", download=program)
        if program:
            print(f"FPGA programmed with {bitstream or 'minitpu.bit'}")

        self.dma  = getattr(self.overlay, dma_name or "axi_dma_0")
        self.ctrl = getattr(self.overlay, tpu_name or "tpu_0")
        self.mmio = self.ctrl.mmio
        print(f"TPU HW ready (DMA={dma_name or 'axi_dma_0'}, TPU={tpu_name or 'tpu_0'})")

    def _doorbell(self, mode):
        self.mmio.write(REG_ADDR["tpu_mode"], mode | DOORBELL_BIT)

    def wait_for_flag(self, name, expected=1, poll_delay=0.001, timeout=10.0):
        offset = REG_ADDR[name]
        deadline = time.time() + timeout
        while self.mmio.read(offset) != expected:
            if time.time() > deadline:
                regs = {k: hex(self.mmio.read(v)) for k, v in REG_ADDR.items()}
                raise TimeoutError(f"Timeout waiting for {name}={expected}. Regs: {regs}")
            time.sleep(poll_delay)

    def write_bram(self, addr, values):
        values = np.asarray(values, dtype=np.float32).reshape(-1)
        pad_len = (8 - (values.size % 8)) % 8
        if pad_len > 0:
            values = np.pad(values, (0, pad_len), 'constant', constant_values=0)
            
        buf = allocate(shape=values.shape, dtype=np.float32)
        try:
            self.wait_for_flag("instr_ready")
            self.mmio.write(REG_ADDR["addr_devmem"], addr // 8)
            self.mmio.write(REG_ADDR["length"], values.size // 8)
            self._doorbell(TpuMode.WRITE_BRAM)
            self.wait_for_flag("stream_ready")
            buf[:] = values
            buf.sync_to_device()
            self.dma.sendchannel.transfer(buf)
            _dma_wait(self.dma.sendchannel)
            self.wait_for_flag("instr_ready")
        finally:
            buf.freebuffer()

    def read_bram(self, addr, length):
        beat_length = (length + 7) // 8
        padded_len = beat_length * 8
        buf = allocate(shape=(padded_len,), dtype=np.float32)
        try:
            self.wait_for_flag("instr_ready")
            self.mmio.write(REG_ADDR["addr_devmem"], addr // 8)
            self.mmio.write(REG_ADDR["length"], beat_length)
            self.dma.recvchannel.transfer(buf)
            self._doorbell(TpuMode.READ_BRAM)
            _dma_wait(self.dma.recvchannel)
            buf.invalidate()
            buf.sync_from_device()
            self.wait_for_flag("instr_ready")
            return np.copy(buf[:length])
        finally:
            buf.freebuffer()

    def write_instructions(self, instructions, base_addr=0):
        instructions = np.asarray(instructions, dtype=np.uint64)
        padded_insts = np.zeros((len(instructions), 4), dtype=np.uint64)
        padded_insts[:, 0] = instructions
        flat = padded_insts.reshape(-1)
        buf = allocate(shape=(flat.size,), dtype=np.uint64)
        try:
            self.wait_for_flag("instr_ready")
            self.mmio.write(REG_ADDR["addr_ram"], base_addr)
            self.mmio.write(REG_ADDR["length"], len(instructions))
            self._doorbell(TpuMode.WRITE_IRAM)
            self.wait_for_flag("stream_ready")
            buf[:] = flat
            self.dma.sendchannel.transfer(buf)
            _dma_wait(self.dma.sendchannel)
            self.wait_for_flag("instr_ready")
        finally:
            buf.freebuffer()

    def compute(self, timeout=30.0):
        self.wait_for_flag("instr_ready", timeout=timeout)
        self.mmio.write(REG_ADDR["length"], 0)
        self._doorbell(TpuMode.COMPUTE)
        self.wait_for_flag("instr_ready", timeout=timeout)

    def devmem_to_l2(self, devmem_addr, l2_addr, length):
        self.wait_for_flag("instr_ready")
        self.mmio.write(REG_ADDR["addr_devmem"], devmem_addr)
        self.mmio.write(REG_ADDR["addr_l2"],     l2_addr)
        self.mmio.write(REG_ADDR["length"],      length)
        self._doorbell(TpuMode.DM_TO_L2)
        self.wait_for_flag("instr_ready")

    def l2_to_devmem(self, l2_addr, devmem_addr, length):
        self.wait_for_flag("instr_ready")
        self.mmio.write(REG_ADDR["addr_devmem"], devmem_addr)
        self.mmio.write(REG_ADDR["addr_l2"],     l2_addr)
        self.mmio.write(REG_ADDR["length"],      length)
        self._doorbell(TpuMode.L2_TO_DM)
        self.wait_for_flag("instr_ready")

    def l2_to_l1(self, l2_addr, l1_base_addr, length):
        self.wait_for_flag("instr_ready")
        self.mmio.write(REG_ADDR["addr_ram"],    l1_base_addr)
        self.mmio.write(REG_ADDR["addr_l2"],     l2_addr)
        self.mmio.write(REG_ADDR["length"],      length)
        self._doorbell(TpuMode.L2_TO_L1)
        self.wait_for_flag("instr_ready")

    def l1_to_l2(self, l1_base_addr, l2_addr, length):
        self.wait_for_flag("instr_ready")
        self.mmio.write(REG_ADDR["addr_ram"],    l1_base_addr)
        self.mmio.write(REG_ADDR["addr_l2"],     l2_addr)
        self.mmio.write(REG_ADDR["length"],      length)
        self._doorbell(TpuMode.L1_TO_L2)
        self.wait_for_flag("instr_ready")

def load_instructions(filepath):
    instructions = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                instructions.append(int(line, 16))
    return np.array(instructions, dtype=np.uint64)
