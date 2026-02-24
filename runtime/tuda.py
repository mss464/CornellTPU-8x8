"""
TUDA (Mini-TPU Unified Device Architecture) Library

Provides the host-side API for managing memory and launching static
kernels on the Mini-TPU.
"""

from typing import Optional, Union
import numpy as np
from pathlib import Path

# Try to import TpuDriver; if not on PYNQ, it may fallback or error when instantiated
try:
    from runtime.pynq_host import TpuDriver
except ImportError:
    TpuDriver = None

from runtime.allocator import allocator
from runtime import get_tpu_driver

def host(fn):
    """Decorator to logically demarcate host-side API and orchestration functions."""
    return fn

class TUDADevice:
    def __init__(self, bitstream: Optional[str] = None, program_fpga: bool = True):
        self.driver = get_tpu_driver(bitstream=bitstream, program=program_fpga)
        self.allocator = allocator
    
    @host
    def tudaMalloc(self, name: str, size_words: int) -> int:
        """
        Allocate memory on the TPU BRAM.
        Returns the 13-bit word address.
        """
        return self.allocator.alloc(name, size_words)
    
    @host
    def tudaFree(self, name: str):
        """Free previously allocated memory."""
        self.allocator.free(name)

    @host
    def tudaMemcpy(self, addr: int, data: Union[np.ndarray, int], direction: str = "HostToDevice") -> Optional[np.ndarray]:
        """
        Transfer data between Host (NumPy) and Device (BRAM).
        direction: 'HostToDevice' or 'DeviceToHost'.
        For DeviceToHost, 'data' is interpreted as the length (int) of words to read.
        """
        if direction == "HostToDevice":
            self.driver.write_bram(addr, data)
        elif direction == "DeviceToHost":
            length = data if isinstance(data, int) else data.size
            return self.driver.read_bram(addr, length)
        else:
            raise ValueError(f"Unknown direction: {direction}")

    @host
    def tudaKernelLaunch(self, binary_path: str):
        """
        Load a statically compiled kernel (.tpu_bin) onto the device and execute it.
        Dynamic memory mapping is planned for Phase 2.
        """
        data = np.load(binary_path, allow_pickle=True)
        instructions = data['instructions']
        self.driver.write_instructions(instructions)
        self.driver.compute()

# Global device context
_device = None

@host
def tudaInit(bitstream: Optional[str] = None, program_fpga: bool = True):
    global _device
    _device = TUDADevice(bitstream, program_fpga)
    return _device

@host
def tudaMalloc(name: str, size_words: int) -> int:
    return _device.tudaMalloc(name, size_words)

@host
def tudaMemcpy(addr: int, data: Union[np.ndarray, int], direction: str = "HostToDevice"):
    return _device.tudaMemcpy(addr, data, direction)

@host
def tudaKernelLaunch(binary_path: str):
    _device.tudaKernelLaunch(binary_path)
