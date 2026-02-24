"""
Mock TPU Driver for Unit Testing

Provides a duck-typed simulation of the hardware `TpuDriver` that replaces
physical PYNQ Memory / Registers with simple NumPy arrays. Used for validating 
the RPC loop and host execution flow without needing physical hardware.
"""

import numpy as np

class MockTpuDriver:
    """Mock driver class for Mini-TPU hardware interface."""

    def __init__(self, mem_size_words=8192):
        print("Initializing MOCK TPU Driver...")
        self.bram = np.zeros(mem_size_words, dtype=np.float32)
        self.iram = np.zeros(mem_size_words, dtype=np.uint64)
        print("Mock TPU HW ready.")

    def reset(self):
        """Force TPU back to a clean state."""
        self.bram.fill(0)
        self.iram.fill(0)
    
    def write_bram(self, addr: int, values: np.ndarray):
        """Mock BRAM Write"""
        values = np.asarray(values, dtype=np.float32).reshape(-1)
        length = len(values)
        if addr + length > len(self.bram):
            raise MemoryError(f"OOB Mock Write: {addr}+{length}")
        self.bram[addr:addr+length] = values
        print(f"[MOCK] Wrote {length} floats to BRAM[{addr}]")
    
    def read_bram(self, addr: int, length: int) -> np.ndarray:
        """Mock BRAM Read"""
        if addr + length > len(self.bram):
            raise MemoryError(f"OOB Mock Read: {addr}+{length}")
        arr = self.bram[addr:addr+length].copy()
        print(f"[MOCK] Read {length} floats from BRAM[{addr}]")
        return arr
    
    def write_instructions(self, instructions: np.ndarray, base_addr: int = 0):
        """Mock IRAM Write"""
        instructions = np.asarray(instructions, dtype=np.uint64).reshape(-1)
        length = len(instructions)
        if base_addr + length > len(self.iram):
            raise MemoryError(f"OOB Mock IRAM Write: {base_addr}+{length}")
        self.iram[base_addr:base_addr+length] = instructions
        print(f"[MOCK] Wrote {length} instructions to IRAM[{base_addr}]")
    
    def compute(self):
        """Mock Execution"""
        print("[MOCK] Compute triggered.")
        # Optional: For basic integration testing, we could look for a specific 
        # signature or implement a tiny interpreter to actually update BRAM.
        # For now, it just yields success so the RPC loop returns.
