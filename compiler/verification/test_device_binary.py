"""
Test proper creation and saving of pure TPUDeviceBinary (.tpu_bin) format.
"""

import os
import sys
import numpy as np
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from compiler.compile import kernel, Param, Program
from compiler.executable import TPUDeviceBinary
from compiler.instructions import vadd, vload, vstore

def test_device_binary():
    print("Testing pure TPUDeviceBinary pipeline...")
    @kernel
    def simple_add(A: Param, B: Param, C: Param):
        vload(0, A)
        vload(1, B)
        vadd(2, 0, 1)
        vstore(2, C)

    prog = Program()
    addr_a = prog.alloc("A", 8)
    addr_b = prog.alloc("B", 8)
    addr_c = prog.alloc("C", 8)

    prog.call(simple_add, A=addr_a, B=addr_b, C=addr_c)
    
    binary_data = prog.compile()
    memory_map = prog.get_memory_map()
    
    binary = TPUDeviceBinary(instructions=binary_data, memory_map=memory_map)
    
    test_path = Path("compiler/verification/test_simple.tpu_bin")
    binary.save(test_path)
    
    assert test_path.exists(), "Binary file was not created"

    loaded = TPUDeviceBinary.load(test_path)
    assert len(loaded.instructions) == len(binary.instructions)
    assert "A" in loaded.memory_map
    
    if test_path.exists():
        os.remove(test_path)
        
    print("[SUCCESS] TPUDeviceBinary test passed!")

if __name__ == "__main__":
    try:
        test_device_binary()
    except Exception as e:
        print(f"\n[FAILURE] Device binary test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
