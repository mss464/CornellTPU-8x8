"""
Unit tests for Mini-TPU Codegen and Instruction logic.
Verifies bit-level encoding and IR consistency.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from compiler.compile import encode_vpu, encode_systolic, encode_halt
from compiler.instructions import get_instruction_log, clear_instruction_log, vadd

def test_encoding():
    print("Testing Encoder...")
    # Test Halt
    assert encode_halt() == 0xF000000000000000
    
    # Test VPU Add (Opcode 0)
    # [0][0][addrA][addrB][addrOut][0]
    # addrA=1, addrB=2, addrOut=3
    # Shift bits: opcode=56, a=42, b=28, out=14
    expected = (0 << 56) | (1 << 42) | (2 << 28) | (3 << 14)
    assert encode_vpu("add", 1, 2, 3) == expected

    # Test Systolic (Opcode 1)
    # [1][w][x][z][len]
    # w=1, x=2, z=3, len=16
    # Shift bits: type=60, w=46, x=32, z=18
    expected = (1 << 60) | (1 << 46) | (2 << 32) | (3 << 18) | 16
    assert encode_systolic(1, 2, 3, 16) == expected
    
    print("  Encoding tests passed.")

def test_tracing():
    print("Testing IR Tracing...")
    clear_instruction_log()
    vadd(0, 1, 2)
    log = get_instruction_log()
    assert len(log) == 1
    assert log[0] == "vadd 0, 1, 2, False"
    print("  Tracing tests passed.")

if __name__ == "__main__":
    try:
        test_encoding()
        test_tracing()
        print("\n[SUCCESS] Codegen/ISA Tests Passed!")
    except Exception as e:
        print(f"\n[FAILURE] ISA test failed: {e}")
        sys.exit(1)
