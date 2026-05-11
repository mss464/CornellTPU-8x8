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
    "mode":          0x00,   # [3:0]=mode, [4]=doorbell
    "compute_idle":  0x04,   # bit 0 = compute channel idle
    "dma_idle":      0x08,   # bit 0 = DMA channel idle
    "stream_ready":  0x08,   # bit 1 = DMA stream ready
    "addr_sys":      0x0C,   # slv_reg3: system memory base address (word addr)
    "addr_onchip":   0x10,   # slv_reg4: on-chip memory base address (word addr)
    "length":        0x18,   # slv_reg6: transfer length in 32-bit words
    "debug_stream":  0x34,   # slv_reg13: debug stream
    "debug_mc":      0x38,   # slv_reg14: debug mc
}

DOORBELL_BIT = 0x10  # bit 4 of mode register

DMA_TRANSFER_TIMEOUT = 8.0  # seconds

DMA_SR_ERR     = 0x0070
DMA_SR_IOC_IRQ = 0x1000
DMA_SR_IRQS    = 0x7000


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
    COMPUTE    = 3   # Trigger TPU compute execution
    WRITE_IRAM = 4   # Host → Instruction RAM via AXI-Stream
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
                 axi_full_name=None, program=False, latency_mode=0):
        self.latency_mode = latency_mode
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
                print(f"DEBUG: Searching for AXI-Full MMIO in {len(ip_dict)} segments...")
                for name, info in ip_dict.items():
                    full = str(info.get('fullname', '')).lower()
                    # Segment size for s01_axi is 256KB (0x40000)
                    size = info.get('addr_range', 0)
                    
                    if ('s01' in full or 's01' in name.lower() or 
                        (size == 0x40000 and name != self.ctrl.fullname)):
                        base = info['phys_addr']
                        self.axi_full_mmio = MMIO(base, size)
                        print(f"AXI-Full MMIO detected: {name} @ 0x{base:08X} (size=0x{size:X})")
                        break
                
                if self.axi_full_mmio is None:
                    print("DEBUG: Available segments:")
                    for name, info in ip_dict.items():
                        print(f"  - {name}: 0x{info['phys_addr']:08X} (size=0x{info['addr_range']:X}, fullname={info.get('fullname','')})")
            except Exception:
                pass

        if self.axi_full_mmio is None:
            print("WARNING: AXI4-Full MMIO port not found — 'mmio' method "
                  "will fall back to DMA. Use 'dma' method for transfers.")

        self.debug_dma = os.environ.get("MINITPU_DEBUG_DMA", "").lower() in (
            "1", "true", "yes", "on"
        )
        self._dma_tx_buf = None
        self._dma_rx_buf = None

    def _debug(self, msg):
        if self.debug_dma:
            print(msg)

    def _get_dma_buffer(self, name, words, dtype=np.float32):
        """Reuse PYNQ buffers to avoid per-transfer allocation overhead."""
        buf = getattr(self, name, None)
        if buf is None or buf.size < words or buf.dtype != np.dtype(dtype):
            if buf is not None:
                try:
                    buf.freebuffer()
                except Exception:
                    pass
            buf = allocate(shape=(int(words),), dtype=dtype, cacheable=False)
            setattr(self, name, buf)
        return buf

    @staticmethod
    def _sync_to_device_if_needed(buf):
        if getattr(buf, "cacheable", True) is False:
            return
        if hasattr(buf, "sync_to_device"):
            buf.sync_to_device()

    @staticmethod
    def _sync_from_device_if_needed(buf):
        if getattr(buf, "cacheable", True) is False:
            return
        if hasattr(buf, "sync_from_device"):
            buf.sync_from_device()

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
        # slv_reg0: [3:0]=mode, [4]=doorbell, [7]=latency_mode
        val = (self.latency_mode << 7) | DOORBELL_BIT | (mode & 0xF)
        self.mmio.write(REG_ADDR["mode"], val)
        # Read back as an AXI-Lite ordering barrier. The doorbell bit may
        # already be auto-cleared by hardware, so do not validate its value.
        self.mmio.read(REG_ADDR["mode"])
        time.sleep(1e-6)

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
        """Wait until BOTH DMA and Compute channels are idle."""
        deadline = time.time() + timeout
        while True:
            compute_idle = self.mmio.read(REG_ADDR["compute_idle"]) & 1
            dma_idle     = self.mmio.read(REG_ADDR["dma_idle"]) & 1
            if compute_idle and dma_idle:
                return
            if time.time() > deadline:
                regs = {k: hex(self.mmio.read(v)) for k, v in REG_ADDR.items()}
                raise TimeoutError(f"Timeout waiting for idle. Regs: {regs}")
            time.sleep(poll_delay)

    def wait_stream_ready(self, poll_delay=0.0001, timeout=5.0):
        """Wait until the TPU is ready for AXI-Stream transfer."""
        offset = REG_ADDR["stream_ready"]
        deadline = time.time() + timeout
        while (self.mmio.read(offset) & 2) != 2: # bit 1
            if time.time() > deadline:
                raise TimeoutError("Timeout waiting for stream_ready (TPU FSM hang?)")
            time.sleep(poll_delay)

    def wait_compute_idle(self, poll_delay=0.001, timeout=10.0):
        """Wait until the Compute channel is idle (DMA may still be running)."""
        offset = REG_ADDR["compute_idle"]
        deadline = time.time() + timeout
        while not (self.mmio.read(offset) & 1):
            if time.time() > deadline:
                raise TimeoutError("Timeout waiting for compute_idle")
            time.sleep(poll_delay)

    def wait_dma_idle(self, poll_delay=0.001, timeout=10.0):
        """Wait until the DMA channel is idle (Compute may still be running)."""
        offset = REG_ADDR["dma_idle"]
        deadline = time.time() + timeout
        while not (self.mmio.read(offset) & 1):
            if time.time() > deadline:
                regs = {k: hex(self.mmio.read(v)) for k, v in REG_ADDR.items()}
                raise TimeoutError(f"Timeout waiting for dma_idle. Regs: {regs}")
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
        nbytes = values.size * 4  # float32 = 4 bytes
        buf = self._get_dma_buffer("_dma_tx_buf", values.size, np.float32)
        try:
            self.wait_dma_idle()
            self._write_reg("addr_sys", addr)
            # Hardware register is in 32-bit words; mem_top converts to beats.
            self._write_reg("length", values.size)
            if self.debug_dma:
                reg3_rb = self.mmio.read(0x0C)
                reg6_rb = self.mmio.read(0x18)
                self._debug(f"DEBUG WRITE: addr={addr} words={values.size} beats={beat_length} reg3_rb={reg3_rb} reg6_rb={reg6_rb}")
            buf[:values.size] = values
            self._sync_to_device_if_needed(buf)
            self._doorbell(Mode.DMA_WRITE)

            # ── Manual MM2S setup ──
            # 1. Reset MM2S and wait for it to clear
            self.dma.write(0x00, 0x4)
            for _ in range(200):
                if not (self.dma.read(0x00) & 0x4): break
                time.sleep(0.0001)
            else:
                raise RuntimeError("MM2S reset did not clear")

            # 2. Clear reset, enable IOC, run
            self.dma.write(0x04, DMA_SR_IRQS)  # clear stale status IRQs
            self.dma.write(0x00, 0x10001)  # RS=1, IOC_IrqEn=1
            cr_rb = self.dma.read(0x00)
            if not (cr_rb & 1):
                raise RuntimeError(f"MM2S failed to start: CR=0x{cr_rb:08X}")
            self.wait_stream_ready() # Wait for TPU to be ready for the stream
            # 3. Set source address
            self.dma.write(0x18, buf.physical_address & 0xFFFFFFFF)
            self.dma.write(0x1C, (buf.physical_address >> 32) & 0xFFFFFFFF)
            self._debug(f"DEBUG SEND: phys=0x{buf.physical_address:x} nbytes={nbytes}")
            # 4. Set transfer length (triggers MM2S)
            self.dma.write(0x28, nbytes)

            # Poll MM2S for completion
            deadline = time.time() + DMA_TRANSFER_TIMEOUT
            while True:
                sr = self.dma.read(0x04)
                if sr & DMA_SR_IOC_IRQ:
                    break
                if sr & DMA_SR_ERR:
                    raise RuntimeError(f"MM2S error: SR=0x{sr:08X}")
                if time.time() > deadline:
                    debug_stream = self.mmio.read(REG_ADDR["debug_stream"])
                    debug_mc     = self.mmio.read(REG_ADDR["debug_mc"])
                    dma_idle_reg = self.mmio.read(REG_ADDR["dma_idle"])
                    cr = self.dma.read(0x00)
                    self.dma.write(0x00, 0x4)  # reset
                    time.sleep(0.01)
                    raise TimeoutError(
                        f"SEND DMA TIMEOUT: MM2S_CR=0x{cr:08X} MM2S_SR=0x{sr:08X} | "
                        f"dma_idle_reg=0x{dma_idle_reg:08X} | "
                        f"Stream(Slave): state={(debug_stream>>19)&1} t_last={(debug_stream>>18)&1} wren={(debug_stream>>17)&1} tready={(debug_stream>>16)&1} ptr={debug_stream&0xFF} | "
                        f"MC: state={(debug_mc>>16)&0x7} issued={debug_mc&0xFF}"
                    )
                time.sleep(0.0001)

            # Acknowledge interrupt
            self.dma.write(0x04, 0x1000)
            if self.debug_dma:
                mm2s_sr = hex(self.dma.read(0x04))
                self._debug(f"DEBUG SEND: MM2S_SR={mm2s_sr} BYTES={nbytes}")
            self.wait_dma_idle()
        finally:
            pass

    def _read_dma(self, addr, length):
        """Read from system memory via AXI-Stream DMA."""
        beat_length = (length + 7) // 8
        padded_len = beat_length * 8
        nbytes = padded_len * 4  # float32 = 4 bytes
        buf = self._get_dma_buffer("_dma_rx_buf", padded_len, np.float32)
        if self.debug_dma:
            buf[:padded_len] = 42.42
            self._sync_to_device_if_needed(buf)
        self._debug(f"DEBUG READ: addr={addr} len={length} padded={padded_len} phys={hex(buf.physical_address)}")
        try:
            self.wait_dma_idle()

            # ── Manual S2MM setup (bypass broken PYNQ channel state) ──
            # 1. Reset S2MM channel and wait for it to clear
            self.dma.write(0x30, 0x4)
            for _ in range(100):
                if not (self.dma.read(0x30) & 0x4): break
                time.sleep(0.0001)

            # 2. Clear reset, enable IOC interrupt
            self.dma.write(0x34, DMA_SR_IRQS)  # clear stale status IRQs
            self.dma.write(0x30, 0x10001)  # RS=1, IOC_IrqEn=1
            for _ in range(100):
                if not (self.dma.read(0x34) & 0x1): break
                time.sleep(0.00001)
            # 3. Set destination address
            self.dma.write(0x48, buf.physical_address & 0xFFFFFFFF)
            self.dma.write(0x4C, (buf.physical_address >> 32) & 0xFFFFFFFF)
            # 4. Set transfer length (triggers S2MM)
            self.dma.write(0x58, nbytes)

            if self.debug_dma:
                s2mm_sr = self.dma.read(0x34)
                self._debug(f"DEBUG READ: S2MM started, SR=0x{s2mm_sr:08X}")

            # Now tell FPGA to start streaming
            self._write_reg("addr_sys", addr)
            # Hardware register is in 32-bit words; mem_top converts to beats.
            self._write_reg("length", padded_len)
            self._doorbell(Mode.DMA_READ)
            self.wait_stream_ready()

            # Poll S2MM status for real completion. Idle alone is not enough:
            # an idle channel with no IOC means the stream never wrote this buf.
            deadline = time.time() + DMA_TRANSFER_TIMEOUT
            while True:
                sr = self.dma.read(0x34)
                if sr & DMA_SR_IOC_IRQ:
                    break
                if sr & DMA_SR_ERR:  # any error bit
                    raise RuntimeError(f"S2MM error during read: SR=0x{sr:08X}")
                if time.time() > deadline:
                    debug_stream = self.mmio.read(REG_ADDR["debug_stream"])
                    debug_mc     = self.mmio.read(REG_ADDR["debug_mc"])
                    self.dma.write(0x30, 0x4)
                    time.sleep(0.01)
                    raise TimeoutError(
                        f"RECV DMA TIMEOUT: S2MM_SR=0x{sr:08X} | "
                        f"Stream: state={(debug_stream>>20)&0x3} empty={(debug_stream>>13)&1} full={(debug_stream>>12)&1} sent={debug_stream&0xFF} | "
                        f"MC: state={(debug_mc>>16)&0x7} issued={debug_mc&0xFF}"
                    )
                time.sleep(0.0001)

            # Acknowledge interrupt
            if self.debug_dma:
                debug_stream = self.mmio.read(REG_ADDR["debug_stream"])
                debug_mc     = self.mmio.read(REG_ADDR["debug_mc"])
                self._debug(
                    f"DEBUG READ DONE: S2MM_SR=0x{sr:08X} | "
                    f"Stream: state={(debug_stream>>20)&0x3} empty={(debug_stream>>13)&1} full={(debug_stream>>12)&1} sent={debug_stream&0xFF} | "
                    f"MC: state={(debug_mc>>16)&0x7} issued={debug_mc&0xFF}"
                )
            self.dma.write(0x34, 0x1000)

            if hasattr(buf, "invalidate") and getattr(buf, "cacheable", True):
                buf.invalidate()
            self._sync_from_device_if_needed(buf)
            self.wait_dma_idle()
            return np.copy(buf[:length])
        finally:
            pass

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
        """Trigger sys_mem[sys_addr] -> on-chip_mem[oc_addr] copy (Mode 5).
        WARNING: This uses scratchpad Port A — must NOT run concurrently with compute.
        """
        self.wait_idle()  # wait for BOTH channels (port conflict with compute)
        self._write_reg("addr_sys",    sys_addr)
        self._write_reg("addr_onchip", oc_addr)
        self._write_reg("length",      length)
        self._doorbell(Mode.SYS_TO_OC)
        self.wait_dma_idle()

    def onchip_to_sysmem(self, oc_addr, sys_addr, length):
        """Trigger on-chip_mem[oc_addr] -> sys_mem[sys_addr] copy (Mode 6).
        WARNING: This uses scratchpad Port A — must NOT run concurrently with compute.
        """
        self.wait_idle()  # wait for BOTH channels (port conflict with compute)
        self._write_reg("addr_onchip", oc_addr)
        self._write_reg("addr_sys",    sys_addr)
        self._write_reg("length",      length)
        self._doorbell(Mode.OC_TO_SYS)
        self.wait_dma_idle()

    # ── Compute Tile API ──────────────────────────────────────────────────

    def load_instructions(self, instructions):
        """Load a list of 32-bit instruction words into the TPU's IRAM.
        Instructions are sent via AXI-Stream (Mode 4).
        """
        instr_words = np.asarray(instructions, dtype=np.uint32).reshape(-1)
        if instr_words.size % 2 != 0:
            raise ValueError("Instruction stream must contain low/high 32-bit word pairs")

        # The RTL writes S_AXIS_TDATA[63:0] into one IRAM entry per 256-bit beat.
        # Pack each 64-bit instruction into the low two words of its own beat.
        beat_words = np.zeros((instr_words.size // 2) * 8, dtype=np.uint32)
        beat_words[0::8] = instr_words[0::2]
        beat_words[1::8] = instr_words[1::2]
        data = beat_words.view(np.float32)

        nbytes = data.size * 4
        buf = allocate(shape=data.shape, dtype=np.float32, cacheable=False)
        try:
            self.wait_dma_idle()
            buf[:] = data
            buf.sync_to_device()

            self._write_reg("length", data.size)
            self._doorbell(Mode.WRITE_IRAM)

            # Trigger DMA MM2S
            self.dma.write(0x00, 0x4)
            for _ in range(100):
                if not (self.dma.read(0x00) & 0x4): break
                time.sleep(0.0001)
            self.dma.write(0x04, DMA_SR_IRQS)
            self.dma.write(0x00, 0x10001) # RS=1, IOC_IrqEn=1
            self.wait_stream_ready()
            self.dma.write(0x18, buf.physical_address & 0xFFFFFFFF)
            self.dma.write(0x1C, (buf.physical_address >> 32) & 0xFFFFFFFF)
            self.dma.write(0x28, nbytes)

            deadline = time.time() + DMA_TRANSFER_TIMEOUT
            while True:
                sr = self.dma.read(0x04)
                if sr & DMA_SR_IOC_IRQ:
                    break
                if sr & DMA_SR_ERR:
                    raise RuntimeError(f"IRAM MM2S error: SR=0x{sr:08X}")
                if time.time() > deadline:
                    raise TimeoutError(f"IRAM DMA transfer timed out: MM2S_SR=0x{sr:08X}")
                time.sleep(0.0001)
            self.dma.write(0x04, DMA_SR_IOC_IRQ) # ACK
            self.wait_dma_idle()
        finally:
            buf.freebuffer()

    def run_compute(self, timeout=10.0, async_run=False):
        """Trigger TPU execution of instructions currently in IRAM (Mode 3).
        If async_run=True, returns immediately after triggering.
        """
        self.wait_compute_idle()
        self._doorbell(Mode.COMPUTE)
        if not async_run:
            self.wait_compute_idle(timeout=timeout)

    def send_bytes_async(self, addr, data):
        """Write data to L2 via DMA without waiting for Compute to finish.

        This is the key double-buffering API: the host can load the next
        tile of data into L2 while the compute core is still executing
        on the current tile in L1.

        Only waits for the DMA channel to be idle before starting.
        """
        self.send_bytes(addr, data, method='dma')


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
