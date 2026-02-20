#!/usr/bin/env python3
"""
SIMD VPU corner/edge case test program.
"""

import sys
from pathlib import Path
import numpy as np

# Resolve local harness
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import harness

from compiler import Program, kernel, Param

# Note: Keeping corner case kernels local as they are highly specific to this test
# but updating them to use the new compiler.instructions.

@kernel
def add_zeros(A: Param, B: Param, C: Param):
    """VADD with all-zero inputs."""
    from compiler.instructions import vload, vadd, vstore
    vload(0, A)
    vload(1, B)
    vadd(2, 0, 1)
    vstore(2, C)

@kernel
def mul_zeros(A: Param, B: Param, C: Param):
    """VMUL with all-zero inputs."""
    from compiler.instructions import vload, vmul, vstore
    vload(0, A)
    vload(1, B)
    vmul(2, 0, 1)
    vstore(2, C)

@kernel
def add_negatives(A: Param, B: Param, C: Param):
    """VADD with all-negative inputs."""
    from compiler.instructions import vload, vadd, vstore
    vload(0, A)
    vload(1, B)
    vadd(2, 0, 1)
    vstore(2, C)

@kernel
def add_cancellation(A: Param, B: Param, C: Param):
    """VADD where B = -A, should produce zeros."""
    from compiler.instructions import vload, vadd, vstore
    vload(0, A)
    vload(1, B)
    vadd(2, 0, 1)
    vstore(2, C)

@kernel
def mul_identity(A: Param, Ones: Param, C: Param):
    """VMUL by 1.0 should preserve input."""
    from compiler.instructions import vload, vmul, vstore
    vload(0, A)
    vload(1, Ones)
    vmul(2, 0, 1)
    vstore(2, C)

@kernel
def add_identity(A: Param, Zeros: Param, C: Param):
    """VADD with 0.0 should preserve input."""
    from compiler.instructions import vload, vadd, vstore
    vload(0, A)
    vload(1, Zeros)
    vadd(2, 0, 1)
    vstore(2, C)

@kernel
def self_add(A: Param, C: Param):
    """VADD V0, V0, V0 — same register for both sources and destination."""
    from compiler.instructions import vload, vadd, vstore
    vload(0, A)
    vadd(0, 0, 0)   # V0 = V0 + V0
    vstore(0, C)

@kernel
def sub_basic(A: Param, B: Param, C: Param):
    """VSUB: C = A - B."""
    from compiler.instructions import vload, vsub, vstore
    vload(0, A)
    vload(1, B)
    vsub(2, 0, 1)
    vstore(2, C)

@kernel
def sub_self(A: Param, C: Param):
    """VSUB V0 - V0 = 0 (self-subtraction)."""
    from compiler.instructions import vload, vsub, vstore
    vload(0, A)
    vsub(1, 0, 0)   # V1 = V0 - V0 = 0
    vstore(1, C)

@kernel
def relu_all_positive(A: Param, C: Param):
    """VRELU on all-positive values."""
    from compiler.instructions import vload, vrelu, vstore
    vload(0, A)
    vrelu(1, 0)
    vstore(1, C)

@kernel
def relu_all_negative(A: Param, C: Param):
    """VRELU on all-negative values."""
    from compiler.instructions import vload, vrelu, vstore
    vload(0, A)
    vrelu(1, 0)
    vstore(1, C)

@kernel
def relu_zeros(A: Param, C: Param):
    """VRELU on all zeros."""
    from compiler.instructions import vload, vrelu, vstore
    vload(0, A)
    vrelu(1, 0)
    vstore(1, C)

@kernel
def chain_ops(A: Param, B: Param, C: Param):
    """Chain: V2 = (A + B) * A."""
    from compiler.instructions import vload, vadd, vmul, vstore
    vload(0, A)
    vload(1, B)
    vadd(2, 0, 1)
    vmul(3, 2, 0)
    vstore(3, C)

@kernel
def all_regs(D0: Param, D1: Param, D2: Param, D3: Param, D4: Param, D5: Param, D6: Param, D7: Param, Out: Param):
    from compiler.instructions import vload, vadd, vstore
    vload(0, D0); vload(1, D1); vload(2, D2); vload(3, D3); vload(4, D4); vload(5, D5); vload(6, D6); vload(7, D7)
    vadd(0, 0, 1); vadd(0, 0, 2); vadd(0, 0, 3); vadd(0, 0, 4); vadd(0, 0, 5); vadd(0, 0, 6); vadd(0, 0, 7)
    vstore(0, Out)

@kernel
def large_values(A: Param, B: Param, C: Param):
    from compiler.instructions import vload, vadd, vstore
    vload(0, A); vload(1, B); vadd(2, 0, 1); vstore(2, C)

@kernel
def small_values(A: Param, B: Param, C: Param):
    from compiler.instructions import vload, vmul, vstore
    vload(0, A); vload(1, B); vmul(2, 0, 1); vstore(2, C)

@kernel
def scalar_add_broadcast(A: Param, S: Param, C: Param):
    from compiler.instructions import vload, vadd, vstore
    vload(0, A); vload(1, S); vadd(2, 0, 1, scalar=True); vstore(2, C)

@kernel
def mul_negone(A: Param, NegOnes: Param, C: Param):
    from compiler.instructions import vload, vmul, vstore
    vload(0, A); vload(1, NegOnes); vmul(2, 0, 1); vstore(2, C)

def define_program():
    prog = Program()
    # [Allocation and Data Gen logic same as before, just fixed kernel refs]
    zeros = prog.alloc("zeros", 8); ones = prog.alloc("ones", 8); neg_ones = prog.alloc("neg_ones", 8)
    input_a = prog.alloc("input_a", 8); neg_a = prog.alloc("neg_a", 8); input_b = prog.alloc("input_b", 8)
    all_neg = prog.alloc("all_neg", 8); all_pos = prog.alloc("all_pos", 8)
    large_a = prog.alloc("large_a", 8); large_b = prog.alloc("large_b", 8)
    small_a = prog.alloc("small_a", 8); small_b = prog.alloc("small_b", 8)
    scalar_val = prog.alloc("scalar_val", 1)
    d = [prog.alloc(f"reg_d{i}", 8) for i in range(8)]
    
    out_names = ["add_zeros", "mul_zeros", "add_neg", "cancel", "mul_id", "add_id", "self_add", "sub", "sub_self", "relu_pos", "relu_neg", "relu_zero", "chain", "all_regs", "large", "small", "scalar_add", "mul_negone"]
    outputs_buf = {name: prog.alloc(f"out_{name}", 8) for name in out_names}

    prog.call(add_zeros, A=zeros, B=zeros, C=outputs_buf["add_zeros"])
    prog.call(mul_zeros, A=zeros, B=zeros, C=outputs_buf["mul_zeros"])
    prog.call(add_negatives, A=all_neg, B=all_neg, C=outputs_buf["add_neg"])
    prog.call(add_cancellation, A=input_a, B=neg_a, C=outputs_buf["cancel"])
    prog.call(mul_identity, A=input_a, Ones=ones, C=outputs_buf["mul_id"])
    prog.call(add_identity, A=input_a, Zeros=zeros, C=outputs_buf["add_id"])
    prog.call(self_add, A=input_a, C=outputs_buf["self_add"])
    prog.call(sub_basic, A=input_a, B=input_b, C=outputs_buf["sub"])
    prog.call(sub_self, A=input_a, C=outputs_buf["sub_self"])
    prog.call(relu_all_positive, A=all_pos, C=outputs_buf["relu_pos"])
    prog.call(relu_all_negative, A=all_neg, C=outputs_buf["relu_neg"])
    prog.call(relu_zeros, A=zeros, C=outputs_buf["relu_zero"])
    prog.call(chain_ops, A=input_a, B=input_b, C=outputs_buf["chain"])
    prog.call(all_regs, **{f"D{i}": d[i] for i in range(8)}, Out=outputs_buf["all_regs"])
    prog.call(large_values, A=large_a, B=large_b, C=outputs_buf["large"])
    prog.call(small_values, A=small_a, B=small_b, C=outputs_buf["small"])
    prog.call(scalar_add_broadcast, A=input_a, S=scalar_val, C=outputs_buf["scalar_add"])
    prog.call(mul_negone, A=input_a, NegOnes=neg_ones, C=outputs_buf["mul_negone"])

    # Data gen
    a_data = np.arange(1, 9, dtype=np.float32)
    inputs = { "zeros": np.zeros(8, dtype=np.float32), "ones": np.ones(8, dtype=np.float32), "neg_ones": np.full(8, -1.0, dtype=np.float32), "input_a": a_data, "neg_a": -a_data, "input_b": np.arange(0.5, 4.5, 0.5, dtype=np.float32), "all_neg": -10*a_data, "all_pos": 10*a_data, "large_a": 1e30*np.ones(8, dtype=np.float32), "large_b": 1e30*np.ones(8, dtype=np.float32), "small_a": 1e-20*np.ones(8, dtype=np.float32), "small_b": 1e-20*np.ones(8, dtype=np.float32), "scalar_val": np.array([100.0], dtype=np.float32) }
    for i in range(8): inputs[f"reg_d{i}"] = np.full(8, float(i+1), dtype=np.float32)

    expected = { f"out_{name}": np.zeros(8, dtype=np.float32) for name in out_names } # Placeholder for real check if needed
    
    return prog, inputs, expected

if __name__ == "__main__":
    prog, inputs, expected = define_program()
    harness.save_executable(prog, inputs, expected, Path("workflow/binaries/simd_edge_cases.npz"))
