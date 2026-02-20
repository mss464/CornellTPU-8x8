"""
Software Simulator HAL - CPU-based reference implementation.

[PLANNED] This module will provide:
- Cycle-accurate simulation of TPU instructions
- Golden reference for testing other HAL implementations
- Debugging and profiling support
"""

import numpy as np
from runtime.device import TPUDevice, DeviceBuffer, Execution


class CompletedExecution(Execution):
    """Execution handle for synchronous (already-complete) operations."""
    pass


class SimulatorDevice(TPUDevice):
    """
    Software simulation backend.
    
    Executes TPU instructions on the CPU, providing a golden
    reference for all other HAL implementations.
    """
    
    def __init__(self, memory_size: int = 8192):
        self._memory_size = memory_size
        self.memory = np.zeros(memory_size, dtype=np.float32)
    
    @property
    def memory_size(self) -> int:
        return self._memory_size
    
    def allocate(self, size: int, addr: int) -> DeviceBuffer:
        # Simulator doesn't need real allocation - memory is pre-allocated
        return DeviceBuffer(addr=addr, size=size)
    
    def transfer_h2d(self, data: np.ndarray, buf: DeviceBuffer) -> None:
        flat = data.astype(np.float32).flatten()
        self.memory[buf.addr : buf.addr + len(flat)] = flat
    
    def transfer_d2h(self, buf: DeviceBuffer, length: int) -> np.ndarray:
        return self.memory[buf.addr : buf.addr + length].copy()
    
    def submit(self, instructions: bytes) -> Execution:
        # TODO: Decode and execute instructions
        raise NotImplementedError("Instruction execution not yet implemented")
    
    def sync(self, execution=None) -> None:
        # Simulator is synchronous - nothing to wait for
        pass
