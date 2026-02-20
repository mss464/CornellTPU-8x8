"""
PYNQ Host Interface for Mini-TPU

This module provides a reusable hardware abstraction layer for interacting
with the Mini-TPU on PYNQ-based FPGA boards.
"""

import time
import os
import json
import numpy as np

try:
    from pynq import Overlay, allocate
except ImportError:
    # Allow import on non-PYNQ systems for development
    Overlay = None
    allocate = None


# TPU Register addresses (AXI-Lite)
REG_ADDR = {
    "tpu_mode":     0x00,
    "instr_ready":  0x04,
    "stream_ready": 0x08,
    "addr_ram":     0x0C,
    "length":       0x18,
}

# TPU operation modes
class TpuMode:
    IDLE       = 0
    WRITE_BRAM = 1
    READ_BRAM  = 2
    COMPUTE    = 3
    WRITE_IRAM = 4


class TpuDriver:
    """Driver class for Mini-TPU hardware interface."""

    def __init__(self, bitstream: str = None, tpu_name: str = None, dma_name: str = None, program: bool = False):
        """
        Initialize TPU driver. Assumes hardware is already programmed by default.
        """
        if Overlay is None:
            raise RuntimeError("pynq library not available - must run on PYNQ board")

        # 1. Load contracts from hw_config.json if available
        # Find project root to locate tpu/hw_config.json
        config = {
            "bitstream": "minitpu.bit",
            "handoff": "minitpu.hwh",
            "tpu_names": ["tpu_0", "tpu_top_0", "tpu"],
            "dma_names": ["axi_dma_0", "axi_dma", "dma"]
        }
        
        # Search for hw_config.json in likely locations
        possible_paths = [
            "hw_config.json",
            "tpu/hw_config.json",
            "../tpu/hw_config.json",
            "/home/xilinx/tpu_deploy/hw_config.json"
        ]
        
        for p in possible_paths:
            if os.path.exists(p):
                with open(p, 'r') as f:
                    try:
                        config.update(json.load(f))
                        print(f"Loaded hardware config from {p}")
                    except json.JSONDecodeError:
                        print(f"Warning: Failed to parse {p}")
                break

        # 2. Resolve bitstream path
        if bitstream is None:
            bitstream = config["bitstream"]
            # Check relative to config file if possible, or common deploy path
            if not os.path.exists(bitstream) and os.path.exists("/home/xilinx/tpu_deploy/" + bitstream):
                bitstream = "/home/xilinx/tpu_deploy/" + bitstream
            elif not os.path.exists(bitstream) and os.path.exists("tpu/" + bitstream):
                 bitstream = "tpu/" + bitstream

        # Verify HWH matching
        hwh_path = os.path.splitext(bitstream)[0] + ".hwh"
        if not os.path.exists(hwh_path):
            # Try to see if it was provided under a different name in config
            alt_hwh = os.path.join(os.path.dirname(bitstream), config["handoff"])
            if os.path.exists(alt_hwh) and alt_hwh != hwh_path:
                print(f"Warning: HWH file found as {alt_hwh} but Overlay expects {hwh_path}. Renaming...")
                try:
                    os.rename(alt_hwh, hwh_path)
                except OSError:
                    print(f"Failed to rename {alt_hwh} to {hwh_path}")

        self.overlay = Overlay(bitstream, download=program)
        if program:
            print(f"FPGA programmed with {bitstream}")

        # 3. Auto-detect IPs
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

        self.dma = getattr(self.overlay, dma_name)
        self.ctrl = getattr(self.overlay, tpu_name)
        self.mmio = self.ctrl.mmio

        self.reset()
        print(f"TPU HW ready (DMA={dma_name}, TPU={tpu_name})")

    def reset(self):
        """Force TPU back to a clean state and clear hanging transactions."""
        self.mmio.write(REG_ADDR["tpu_mode"], TpuMode.IDLE)
        time.sleep(0.01)
    
    def wait_for_flag(self, name: str, expected: int = 1, poll_delay: float = 0.001, timeout: float = 5.0):
        """Wait for a TPU status flag to reach expected value."""
        offset = REG_ADDR[name]
        start_time = time.time()
        while self.mmio.read(offset) != expected:
            if time.time() - start_time > timeout:
                 # Read all registers for debug
                 regs = {k: self.mmio.read(v) for k, v in REG_ADDR.items()}
                 raise TimeoutError(f"Timeout waiting for {name}={expected}. Registers: {regs}")
            time.sleep(poll_delay)
    
    def write_bram(self, addr: int, values: np.ndarray):
        """
        Write data to TPU BRAM.
        
        Args:
            addr: Base address in BRAM
            values: numpy array of float32 values to write
        """
        values = np.asarray(values, dtype=np.float32).reshape(-1)
        in_buf = allocate(shape=values.shape, dtype=np.float32)
        
        self.wait_for_flag("instr_ready", 1)
        self.mmio.write(REG_ADDR["addr_ram"], addr)
        self.mmio.write(REG_ADDR["length"], values.size)
        self.mmio.write(REG_ADDR["tpu_mode"], TpuMode.WRITE_BRAM)
        
        self.wait_for_flag("stream_ready", 1)
        in_buf[:] = values
        self.dma.sendchannel.transfer(in_buf)
        self.dma.sendchannel.wait()
        self.wait_for_flag("instr_ready", 1)
        
        in_buf.freebuffer()
        self.mmio.write(REG_ADDR["tpu_mode"], TpuMode.IDLE)
    
    def read_bram(self, addr: int, length: int) -> np.ndarray:
        """
        Read data from TPU BRAM.
        
        Args:
            addr: Base address in BRAM
            length: Number of float32 values to read
            
        Returns:
            numpy array of float32 values
        """
        out_buf = allocate(shape=(length,), dtype=np.float32)
        
        self.wait_for_flag("instr_ready", 1)
        self.mmio.write(REG_ADDR["addr_ram"], addr)
        self.mmio.write(REG_ADDR["length"], length)
        self.mmio.write(REG_ADDR["tpu_mode"], TpuMode.READ_BRAM)
        
        self.dma.recvchannel.transfer(out_buf)
        self.dma.recvchannel.wait()
        
        self.wait_for_flag("instr_ready", 1)
        self.mmio.write(REG_ADDR["tpu_mode"], TpuMode.IDLE)
        
        arr = np.copy(out_buf)
        out_buf.freebuffer()
        return arr
    
    def write_instructions(self, instructions: np.ndarray, base_addr: int = 0):
        """
        Write instruction memory (IRAM).
        
        Args:
            instructions: numpy array of uint64 instruction words
            base_addr: Base address for instruction memory
        """
        instructions = np.asarray(instructions, dtype=np.uint64)
        instr_buf = allocate(shape=instructions.shape, dtype=np.uint64)
        
        self.wait_for_flag("instr_ready", 1)
        self.mmio.write(REG_ADDR["addr_ram"], base_addr)
        # Each 64-bit instruction takes 2 32-bit DMA beats
        self.mmio.write(REG_ADDR["length"], 2 * len(instructions))
        self.mmio.write(REG_ADDR["tpu_mode"], TpuMode.WRITE_IRAM)
        
        self.wait_for_flag("stream_ready", 1)
        instr_buf[:] = instructions
        self.dma.sendchannel.transfer(instr_buf)
        self.dma.sendchannel.wait()
        self.wait_for_flag("instr_ready", 1)
        
        self.mmio.write(REG_ADDR["tpu_mode"], TpuMode.IDLE)
        instr_buf.freebuffer()
    
    def compute(self):
        """Execute the loaded instruction program."""
        self.wait_for_flag("instr_ready", 1)
        self.mmio.write(REG_ADDR["tpu_mode"], TpuMode.COMPUTE)
        self.wait_for_flag("instr_ready", 1)
        self.mmio.write(REG_ADDR["tpu_mode"], TpuMode.IDLE)


def load_instructions(filepath: str) -> np.ndarray:
    """
    Load instruction file (hex format, one instruction per line).
    
    Args:
        filepath: Path to instruction file
        
    Returns:
        numpy array of uint64 instructions
    """
    instructions = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if line:
                instructions.append(int(line, 16))
    return np.array(instructions, dtype=np.uint64)
