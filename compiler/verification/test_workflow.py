"""
Smoke test for the 5-file compiler reorganization.
Validates:
1. Kernel tracing (@kernel)
2. Program composition (Program)
3. Binary codegen (Program.compile)
4. Executable packaging (TPUExecutable)
5. Executable recovery (TPUExecutable.load)
"""

import os
import sys
import numpy as np
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from compiler.compile import kernel, Param, Program
from compiler.executable import TPUExecutable
from compiler.instructions import vadd, vload, vstore

def test_full_pipeline():
    print("Step 1: Defining Kernel...")
    @kernel
    def vector_add_smoketest(A: Param, B: Param, C: Param):
        vload(0, A)
        vload(1, B)
        vadd(2, 0, 1)
        vstore(2, C)

    print("Step 2: Composing Program...")
    prog = Program()
    addr_a = prog.alloc("A", 8)
    addr_b = prog.alloc("B", 8)
    addr_c = prog.alloc("C", 8)

    prog.call(vector_add_smoketest, A=addr_a, B=addr_b, C=addr_c)
    
    print("Step 3: Compiling to Binary...")
    binary = prog.compile()
    assert isinstance(binary, np.ndarray)
    assert binary.dtype == np.uint64
    print(f"  Generated {len(binary)} hardware words.")

    print("Step 4: Packaging Executable...")
    inputs = {"A": np.arange(8, dtype=np.float32), "B": np.arange(8, dtype=np.float32) * 2}
    outputs = {"C": inputs["A"] + inputs["B"]}
    
    exe = TPUExecutable(
        instructions=binary,
        memory_map=prog.get_memory_map(),
        inputs=inputs,
        outputs=outputs,
        metadata={"test": "smoke"}
    )
    
    test_path = Path("compiler/verification/smoke.npz")
    exe.save(test_path)
    assert test_path.exists(), "Executable file was not created"

    print("Step 5: Verifying Load...")
    loaded = TPUExecutable.load(test_path)
    assert len(loaded.instructions) == len(binary)
    assert "A" in loaded.inputs
    assert loaded.metadata["test"] == "smoke"
    print("  Load verification successful.")

    # Cleanup
    if test_path.exists():
        os.remove(test_path)
    
    print("\n[SUCCESS] Compiler Smoke Test Passed!")

if __name__ == "__main__":
    try:
        test_full_pipeline()
    except Exception as e:
        print(f"\n[FAILURE] Smoke test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
