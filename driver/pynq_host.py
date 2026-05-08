"""
PYNQ Host Interface for Memory Subsystem

Provides two data transfer methods:
  - DMA (AXI-Stream): High-bandwidth bulk transfers via PYNQ DMA engine
  - MMIO (AXI4-Full): Direct register-mapped access for small/random transfers

API:
  send_bytes(addr, data, method='dma'|'mmio')  — write to system memory
  read_bytes(addr, length, method='dma'|'mmio') — read from system memory
  sysmem_to_onchip(sys_addr, oc_addr, length)   — internal copy sys→onchip
  onchip_to_sysmem(oc_addr, sys_addr, length)   — internal copy onchip→sys
"""

import time
import os
import json
import struct
import threading
import numpy as np

try:
    from pynq import Overlay, allocate, MMIO
except ImportError:
    Overlay = None
    allocate = None
    MMIO = None

# ── AXI-Lite register offsets ────────────────────────────────────────────────
REG_ADDR = {
    "mode":         0x00,   # [3:0]=mode, [4]=doorbell
    "status":       0x04,   # bit 0 = idle (FSM done)
    "stream_ready": 0x08,   # bit 0 = DMA stream ready
    "addr_sys":     0x0C,   # system memory base address (word addr)
    "addr_onchip":  0x10,   # on-chip memory base address (word addr)
    "length":       0x18,   # transfer length (in 256-bit beats for DMA, words for copy)
    "ddr_phys_base":0x28,   # physical offset for device memory backing (slv_reg10)
}

DOORBELL_BIT = 0x10  # bit 4 of mode register

DMA_TRANSFER_TIMEOUT = 8.0  # seconds


def _dma_wait(channel, timeout=DMA_TRANSFER_TIMEOUT):
    """Wait for a PYNQ DMA channel with a timeout."""
    result = [None]
    exc_holder = [None]

    def _do_wait():
        try:
            channel.wait()
        except Exception as e:
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
        e = exc_holder[0]
        if isinstance(e, RuntimeError):
            try:
                mm2s_cr = hex(channel._mmio.read(0x00))
                mm2s_sr = hex(channel._mmio.read(0x04))
                s2mm_cr = hex(channel._mmio.read(0x30))
                s2mm_sr = hex(channel._mmio.read(0x34))
                e_msg = f"{e} | DMA Regs: MM2S_CR={mm2s_cr}, MM2S_SR={mm2s_sr}, S2MM_CR={s2mm_cr}, S2MM_SR={s2mm_sr}"
                raise RuntimeError(e_msg)
            except Exception as read_ex:
                raise RuntimeError(f"{e} | (Failed to read regs: {read_ex})")
        raise e


# ── Mode constants ───────────────────────────────────────────────────────────
class Mode:
    IDLE       = 0
    DMA_WRITE  = 1   # Host → System Memory via AXI-Stream
    DMA_READ   = 2   # System Memory → Host via AXI-Stream
    SYS_TO_OC  = 5   # System Memory → On-Chip Memory
    OC_TO_SYS  = 6   # On-Chip Memory → System Memory


class MemDriver:
    """PYNQ driver for the memory subsystem FPGA design.

    Provides two access methods to system memory:
      - DMA:  bulk transfers through AXI-Stream (256-bit, high bandwidth)
      - MMIO: single-word register access through AXI4-Full (32-bit, random access)

    Parameters
    ----------
    bitstream : str, optional
        Path to .bit file. Default: 'minitpu.bit'
    mem_name : str, optional
        Name of the mem_top IP in the block design. Default: 'mem_top_0'
    dma_name : str, optional
        Name of the AXI DMA IP. Default: 'axi_dma_0'
    axi_full_name : str, optional
        Name of the AXI4-Full port for MMIO. Default: None (auto-detect)
    program : bool
        Whether to program the FPGA on init. Default: False
    """

    def __init__(self, bitstream=None, mem_name=None, dma_name=None,
                 axi_full_name=None, program=False):
        if Overlay is None:
            raise RuntimeError("pynq library not available")

        bit_path = bitstream or "minitpu.bit"
        self.overlay = Overlay(bit_path, download=program)
        if program:
            print(f"FPGA programmed with {bit_path}")

        # Resolve IP names (try common names)
        mem_names = [mem_name] if mem_name else ["mem_top_0", "tpu_0", "mem_top"]
        dma_names = [dma_name] if dma_name else ["axi_dma_0", "axi_dma", "dma"]

        self.ctrl = None
        for name in mem_names:
            if hasattr(self.overlay, name):
                self.ctrl = getattr(self.overlay, name)
                break
        if self.ctrl is None:
            raise RuntimeError(f"Memory IP not found. Tried: {mem_names}. "
                             f"Available: {dir(self.overlay)}")

        self.dma = None
        for name in dma_names:
            if hasattr(self.overlay, name):
                self.dma = getattr(self.overlay, name)
                break
        if self.dma is None:
            raise RuntimeError(f"DMA IP not found. Tried: {dma_names}")

        if hasattr(self.ctrl, 'mmio'):
            self.mmio = self.ctrl.mmio
        elif hasattr(self.ctrl, 's00_axi'):
            self.mmio = self.ctrl.s00_axi.mmio
        else:
            # Auto-detect MMIO in hierarchy children
            for ip_name in dir(self.ctrl):
                try:
                    child = getattr(self.ctrl, ip_name)
                    if hasattr(child, 'mmio'):
                        self.mmio = child.mmio
                        break
                except Exception:
                    pass
            if getattr(self, 'mmio', None) is None:
                raise RuntimeError(f"Could not find mmio inside {self.ctrl}")
        print(f"Memory subsystem ready (ctrl={self.ctrl}, dma={self.dma})")

        # AXI4-Full MMIO — try to find the memory-mapped region
        # The AXI-Full slave is typically mapped at a separate address
        self.axi_full_mmio = None
        if axi_full_name and hasattr(self.overlay, axi_full_name):
            self.axi_full_mmio = getattr(self.overlay, axi_full_name).mmio
        else:
            # Try to auto-detect from the overlay's IP dict
            try:
                ip_dict = self.overlay.ip_dict
                for name, info in ip_dict.items():
                    if 'fullname' in info and 's01_axi' in str(info.get('fullname', '')):
                        base = info['phys_addr']
                        size = info['addr_range']
                        self.axi_full_mmio = MMIO(base, size)
                        print(f"AXI-Full MMIO: {name} @ 0x{base:08X} (size=0x{size:X})")
                        break
            except Exception:
                pass

        if self.axi_full_mmio is None:
            print("WARNING: AXI4-Full MMIO port not found — 'mmio' method "
                  "will fall back to DMA. Use 'dma' method for transfers.")

        # Allocate backend buffer for device system memory abstraction (1 MB)
        from pynq import allocate
        self.dev_mem_buf = allocate(shape=(1024*1024,), dtype=np.uint8, cacheable=True)
        self.dev_mem_buf[:] = 0 # Now perfectly safe inside cacheable memory
        self.dev_mem_buf.sync_to_device()
        self._write_reg("ddr_phys_base", self.dev_mem_buf.physical_address)

    def _write_reg(self, name, value, verify=True):
        """Write a register to the FSM. 
        Added a tiny sleep to ensure the AXI-Lite interface doesn't drop 
        back-to-back writes.
        """
        offset = REG_ADDR[name]
        self.mmio.write(offset, value)
        time.sleep(1e-6) # 1 microsecond barrier

    def _doorbell(self, mode):
        """Write mode + doorbell bit to trigger the FSM."""
        self.mmio.write(REG_ADDR["mode"], mode | DOORBELL_BIT)

    def _reset_dma_channels(self):
        """Hard-reset both DMA channels to clear any error state."""
        # S2MM reset + restart
        self.dma.write(0x30, 0x4)  # S2MM reset
        time.sleep(0.005)
        self.dma.write(0x30, 0x0)  # clear reset
        time.sleep(0.005)
        # MM2S reset + restart
        self.dma.write(0x00, 0x4)  # MM2S reset
        time.sleep(0.005)
        self.dma.write(0x00, 0x0)  # clear reset
        time.sleep(0.005)

    def wait_idle(self, poll_delay=0.001, timeout=10.0):
        """Wait until the FSM reports idle."""
        offset = REG_ADDR["status"]
        deadline = time.time() + timeout
        while (self.mmio.read(offset) & 1) != 1:
            if time.time() > deadline:
                regs = {k: hex(self.mmio.read(v)) for k, v in REG_ADDR.items()}
                dma_sr = hex(self.dma.read(0x04)) if self.dma else "unknown"
                slv_reg1 = self.mmio.read(0x04)
                dm_state = (slv_reg1 >> 30) & 0x3   # bits 31:30
                dm_aw_done = (slv_reg1 >> 29) & 0x1  # bit 29
                dm_w_done = (slv_reg1 >> 28) & 0x1   # bit 28
                axi_timeout = (slv_reg1 >> 27) & 0x1 # bit 27
                dm_bvalid = (slv_reg1 >> 26) & 0x1   # bit 26
                debug_stream = (slv_reg1 >> 23) & 0x7 # bits 25:23
                write_ptr = (slv_reg1 >> 16) & 0x7F  # bits 22:16
                raise TimeoutError(f"Timeout waiting for idle. Regs: {regs}, "
                                   f"MM2S_SR: {dma_sr}, DBG_STREAM: {bin(debug_stream)}, "
                                   f"WPTR: {write_ptr}, DM_STATE: {dm_state}, "
                                   f"AW_DONE: {dm_aw_done}, W_DONE: {dm_w_done}, "
                                   f"AXI_TIMEOUT: {axi_timeout}, BVALID: {dm_bvalid}")
            time.sleep(poll_delay)

    def wait_stream_ready(self, poll_delay=0.001, timeout=10.0):
        """Wait until the stream interface is ready."""
        offset = REG_ADDR["stream_ready"]
        deadline = time.time() + timeout
        while (self.mmio.read(offset) & 1) != 1:
            if time.time() > deadline:
                raise TimeoutError("Timeout waiting for stream_ready")
            time.sleep(poll_delay)

    # ── Primary API: send_bytes / read_bytes ─────────────────────────────

    def send_bytes(self, addr, data, method='dma'):
        """Write data to system memory.

        Parameters
        ----------
        addr : int
            Word address in system memory (each word = 4 bytes / float32).
            For DMA: must be aligned to 8-word (256-bit) boundary.
        data : array-like
            Data to write. Converted to float32 numpy array.
        method : str
            'dma' for AXI-Stream bulk transfer (fast, 256-bit wide).
            'mmio' for AXI4-Full register writes (slow, random access).
        """
        data = np.asarray(data, dtype=np.float32).reshape(-1)

        if method == 'mmio':
            self._send_mmio(addr, data)
        else:
            self._send_dma(addr, data)

    def read_bytes(self, addr, length, method='dma'):
        """Read data from system memory.

        Parameters
        ----------
        addr : int
            Word address in system memory.
        length : int
            Number of float32 elements to read.
        method : str
            'dma' or 'mmio'.

        Returns
        -------
        np.ndarray
            float32 array of `length` elements.
        """
        if method == 'mmio':
            return self._read_mmio(addr, length)
        else:
            return self._read_dma(addr, length)

    # ── DMA transfer methods ─────────────────────────────────────────────

    def _send_dma(self, addr, values):
        """Write to system memory via AXI-Stream DMA."""
        # Pad to 8-word (256-bit) boundary
        pad_len = (8 - (values.size % 8)) % 8
        if pad_len > 0:
            values = np.pad(values, (0, pad_len), 'constant', constant_values=0)

        beat_length = values.size // 8
        nbytes = values.size * 4
        buf = allocate(shape=values.shape, dtype=np.float32, cacheable=True)
        try:
            self.wait_idle()
            self._write_reg("addr_sys", addr)
            # Hardware expects float32 element count; RTL converts to beats (>>3)
            self._write_reg("length", values.size)
            self._doorbell(Mode.DMA_WRITE)
            self.wait_stream_ready()
            buf[:] = values
            buf.sync_to_device()

            # ── Manual MM2S setup ──
            # 1. Reset MM2S
            self.dma.write(0x00, 0x4)
            time.sleep(0.005)
            # 2. Clear reset, enable IOC, run
            self.dma.write(0x00, 0x10001)  # RS=1, IOC_IrqEn=1
            time.sleep(0.001)
            # 3. Set source address
            self.dma.write(0x18, buf.physical_address & 0xFFFFFFFF)
            self.dma.write(0x1C, (buf.physical_address >> 32) & 0xFFFFFFFF)
            # 4. Set transfer length (triggers MM2S)
            self.dma.write(0x28, nbytes)
            
            time.sleep(0.1) # Let the entire transfer attempt complete
            # Wait for FSM idletion
            deadline = time.time() + DMA_TRANSFER_TIMEOUT
            while True:
                sr = self.dma.read(0x04)
                if sr & 0x1002:  # IOC_Irq or Idle
                    break
                if sr & 0x70:
                    raise RuntimeError(f"MM2S error: SR=0x{sr:08X}")
                if time.time() > deadline:
                    self.dma.write(0x00, 0x4)
                    time.sleep(0.01)
                    raise TimeoutError(f"SEND DMA TIMEOUT: MM2S_SR=0x{sr:08X}")
                time.sleep(0.0001)

            # Acknowledge interrupt
            self.dma.write(0x04, 0x1000)
            self.wait_idle()
        finally:
            buf.freebuffer()

    def _read_dma(self, addr, length):
        """Read from system memory via AXI-Stream DMA."""
        padded_len = ((length + 7) // 8) * 8
        beat_length = padded_len // 8
        nbytes = padded_len * 4  # float32 = 4 bytes
        buf = allocate(shape=(padded_len,), dtype=np.float32, cacheable=True)
        buf[:] = 42.42
        buf.flush()  # Push sentinel to DDR so we can detect DMA overwrites
        print(f"DEBUG READ: addr={addr} len={length} padded={padded_len} phys={hex(buf.physical_address)}")
        try:
            self.wait_idle()

            # ── Manual S2MM setup (bypass broken PYNQ channel state) ──
            # 1. Reset S2MM channel
            self.dma.write(0x30, 0x4)
            time.sleep(0.005)
            # 2. Clear reset, enable IOC interrupt
            self.dma.write(0x30, 0x10001)  # RS=1, IOC_IrqEn=1
            time.sleep(0.001)
            # 3. Set destination address
            self.dma.write(0x48, buf.physical_address & 0xFFFFFFFF)
            self.dma.write(0x4C, (buf.physical_address >> 32) & 0xFFFFFFFF)

            # Start TPU first to buffer data into the stream FIFO.
            # This prevents interconnect deadlocks where S2MM asserts AWVALID 
            # and stalls for data, blocking the TPU's ARVALID reads.
            self._write_reg("addr_sys", addr)
            # Hardware expects float32 element count; RTL converts to beats (>>3)
            self._write_reg("length", padded_len)
            self._doorbell(Mode.DMA_READ)

            # 4. Set transfer length (triggers S2MM)
            self.dma.write(0x58, nbytes)
            time.sleep(0.001)

            s2mm_sr = self.dma.read(0x34)
            s2mm_da = self.dma.read(0x48)
            s2mm_da_msb = self.dma.read(0x4C)
            s2mm_len_reg = self.dma.read(0x58)
            print(f"DEBUG READ: S2MM started, SR=0x{s2mm_sr:08X}")
            print(f"DEBUG READ: S2MM_DA=0x{s2mm_da_msb:08X}_{s2mm_da:08X}, S2MM_LEN={s2mm_len_reg}, buf_phys=0x{buf.physical_address:016X}")

            # Poll S2MM status for completion (IOC_Irq = bit 12, or Idle = bit 1)
            deadline = time.time() + DMA_TRANSFER_TIMEOUT
            while True:
                sr = self.dma.read(0x34)
                if sr & 0x1002:  # IOC_Irq or Idle
                    break
                if sr & 0x70:  # any error bit
                    raise RuntimeError(f"S2MM error during read: SR=0x{sr:08X}")
                if time.time() > deadline:
                    self.dma.write(0x30, 0x4)
                    time.sleep(0.01)
                    raise TimeoutError(f"RECV DMA TIMEOUT: S2MM_SR=0x{sr:08X}")
                time.sleep(0.0001)

            # Acknowledge interrupt

            # Acknowledge interrupt
            self.dma.write(0x34, 0x1000)

            buf.invalidate()  # Invalidate CPU cache to see DMA-written data
            self.wait_idle()
            return np.copy(buf[:length])
        finally:
            buf.freebuffer()

    # ── MMIO transfer methods ────────────────────────────────────────────

    def _send_mmio(self, addr, values):
        """Write to system memory via AXI4-Full MMIO (word-by-word)."""
        if self.axi_full_mmio is None:
            raise RuntimeError("AXI4-Full MMIO not available — use method='dma'")

        raw = values.view(np.uint32)
        for i, val in enumerate(raw):
            byte_addr = (addr + i) * 4  # word addr → byte addr
            self.axi_full_mmio.write(byte_addr, int(val))

    def _read_mmio(self, addr, length):
        """Read from system memory via AXI4-Full MMIO (word-by-word)."""
        if self.axi_full_mmio is None:
            raise RuntimeError("AXI4-Full MMIO not available — use method='dma'")

        result = np.zeros(length, dtype=np.uint32)
        for i in range(length):
            byte_addr = (addr + i) * 4
            result[i] = self.axi_full_mmio.read(byte_addr)
        return result.view(np.float32)

    # ── Internal memory copy API ─────────────────────────────────────────

    def sysmem_to_onchip(self, sys_addr, oc_addr, length):
        """Trigger sys_mem[sys_addr] -> on-chip_mem[oc_addr] copy (Mode 5)."""
        self.wait_idle()
        self._write_reg("addr_sys",    sys_addr)
        self._write_reg("addr_onchip", oc_addr)
        self._write_reg("length",      length)
        self._doorbell(Mode.SYS_TO_OC)
        self.wait_idle()

    def onchip_to_sysmem(self, oc_addr, sys_addr, length):
        """Trigger on-chip_mem[oc_addr] -> sys_mem[sys_addr] copy (Mode 6)."""
        self.wait_idle()
        self._write_reg("addr_onchip", oc_addr)
        self._write_reg("addr_sys",    sys_addr)
        self._write_reg("length",      length)
        self._doorbell(Mode.OC_TO_SYS)
        self.wait_idle()


# ── Backward-compatible aliases (legacy TpuDriver interface) ─────────────
class TpuDriver(MemDriver):
    """Backward-compatible wrapper. Maps old API to new MemDriver."""

    def write_bram(self, addr, values):
        self.send_bytes(addr, values, method='dma')

    def read_bram(self, addr, length):
        return self.read_bytes(addr, length, method='dma')

    def devmem_to_l2(self, devmem_addr, l2_addr, length):
        self.sysmem_to_onchip(devmem_addr, l2_addr, length)

    def l2_to_devmem(self, l2_addr, devmem_addr, length):
        self.onchip_to_sysmem(l2_addr, devmem_addr, length)
