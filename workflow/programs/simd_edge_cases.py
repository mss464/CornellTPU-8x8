#!/usr/bin/env python3
"""
SIMD VPU corner/edge case test program.

Run to compile:
    python tests/ultra96-v2/programs/simd_edge_cases.py

Output:
    tests/ultra96-v2/binaries/simd_edge_cases.npz
"""

import numpy as np
import harness
from compiler.program import Program
from compiler.kernel import kernel, Param


# ============================================================================
# Corner case kernels
# ============================================================================

@kernel
def add_zeros(A: Param, B: Param, C: Param):
    """VADD with all-zero inputs."""
    from compiler.tpu_txt import vload, vadd, vstore
    vload(0, A)
    vload(1, B)
    vadd(2, 0, 1)
    vstore(2, C)


@kernel
def mul_zeros(A: Param, B: Param, C: Param):
    """VMUL with all-zero inputs."""
    from compiler.tpu_txt import vload, vmul, vstore
    vload(0, A)
    vload(1, B)
    vmul(2, 0, 1)
    vstore(2, C)


@kernel
def add_negatives(A: Param, B: Param, C: Param):
    """VADD with all-negative inputs."""
    from compiler.tpu_txt import vload, vadd, vstore
    vload(0, A)
    vload(1, B)
    vadd(2, 0, 1)
    vstore(2, C)


@kernel
def add_cancellation(A: Param, B: Param, C: Param):
    """VADD where B = -A, should produce zeros."""
    from compiler.tpu_txt import vload, vadd, vstore
    vload(0, A)
    vload(1, B)
    vadd(2, 0, 1)
    vstore(2, C)


@kernel
def mul_identity(A: Param, Ones: Param, C: Param):
    """VMUL by 1.0 should preserve input."""
    from compiler.tpu_txt import vload, vmul, vstore
    vload(0, A)
    vload(1, Ones)
    vmul(2, 0, 1)
    vstore(2, C)


@kernel
def add_identity(A: Param, Zeros: Param, C: Param):
    """VADD with 0.0 should preserve input."""
    from compiler.tpu_txt import vload, vadd, vstore
    vload(0, A)
    vload(1, Zeros)
    vadd(2, 0, 1)
    vstore(2, C)


@kernel
def self_add(A: Param, C: Param):
    """VADD V0, V0, V0 — same register for both sources and destination."""
    from compiler.tpu_txt import vload, vadd, vstore
    vload(0, A)
    vadd(0, 0, 0)   # V0 = V0 + V0 (in-place, same reg)
    vstore(0, C)


@kernel
def sub_basic(A: Param, B: Param, C: Param):
    """VSUB: C = A - B."""
    from compiler.tpu_txt import vload, vsub, vstore
    vload(0, A)
    vload(1, B)
    vsub(2, 0, 1)
    vstore(2, C)


@kernel
def sub_self(A: Param, C: Param):
    """VSUB V0 - V0 = 0 (self-subtraction)."""
    from compiler.tpu_txt import vload, vsub, vstore
    vload(0, A)
    vsub(1, 0, 0)   # V1 = V0 - V0 = 0
    vstore(1, C)


@kernel
def relu_all_positive(A: Param, C: Param):
    """VRELU on all-positive values — should be identity."""
    from compiler.tpu_txt import vload, vrelu, vstore
    vload(0, A)
    vrelu(1, 0)
    vstore(1, C)


@kernel
def relu_all_negative(A: Param, C: Param):
    """VRELU on all-negative values — should all become zero."""
    from compiler.tpu_txt import vload, vrelu, vstore
    vload(0, A)
    vrelu(1, 0)
    vstore(1, C)


@kernel
def relu_zeros(A: Param, C: Param):
    """VRELU on all zeros — should remain zero."""
    from compiler.tpu_txt import vload, vrelu, vstore
    vload(0, A)
    vrelu(1, 0)
    vstore(1, C)


@kernel
def chain_ops(A: Param, B: Param, C: Param):
    """Chain: V2 = (A + B) * A — tests multi-step register dependency."""
    from compiler.tpu_txt import vload, vadd, vmul, vstore
    vload(0, A)
    vload(1, B)
    vadd(2, 0, 1)   # V2 = V0 + V1
    vmul(3, 2, 0)   # V3 = V2 * V0 = (A+B)*A
    vstore(3, C)


@kernel
def all_regs(
    D0: Param, D1: Param, D2: Param, D3: Param,
    D4: Param, D5: Param, D6: Param, D7: Param,
    Out: Param,
):
    """Load all 8 registers V0-V7, chain adds, store result.
    V0..V7 = D0..D7, then V0 = V0+V1, V0 = V0+V2, ..., V0 = V0+V7."""
    from compiler.tpu_txt import vload, vadd, vstore
    vload(0, D0)
    vload(1, D1)
    vload(2, D2)
    vload(3, D3)
    vload(4, D4)
    vload(5, D5)
    vload(6, D6)
    vload(7, D7)
    vadd(0, 0, 1)   # V0 = V0 + V1
    vadd(0, 0, 2)   # V0 = V0 + V2
    vadd(0, 0, 3)   # V0 = V0 + V3
    vadd(0, 0, 4)   # V0 = V0 + V4
    vadd(0, 0, 5)   # V0 = V0 + V5
    vadd(0, 0, 6)   # V0 = V0 + V6
    vadd(0, 0, 7)   # V0 = V0 + V7
    vstore(0, Out)


@kernel
def large_values(A: Param, B: Param, C: Param):
    """VADD with large FP32 values near overflow boundary."""
    from compiler.tpu_txt import vload, vadd, vstore
    vload(0, A)
    vload(1, B)
    vadd(2, 0, 1)
    vstore(2, C)


@kernel
def small_values(A: Param, B: Param, C: Param):
    """VMUL with very small FP32 values (near underflow)."""
    from compiler.tpu_txt import vload, vmul, vstore
    vload(0, A)
    vload(1, B)
    vmul(2, 0, 1)
    vstore(2, C)


@kernel
def scalar_add_broadcast(A: Param, S: Param, C: Param):
    """VADD with scalar broadcast: C[i] = A[i] + S[0]."""
    from compiler.tpu_txt import vload, vadd, vstore
    vload(0, A)
    vload(1, S)
    vadd(2, 0, 1, scalar=True)
    vstore(2, C)


@kernel
def mul_negone(A: Param, NegOnes: Param, C: Param):
    """VMUL by -1.0 should negate all values."""
    from compiler.tpu_txt import vload, vmul, vstore
    vload(0, A)
    vload(1, NegOnes)
    vmul(2, 0, 1)
    vstore(2, C)


# ============================================================================
# Build program
# ============================================================================

def build_edge_case_program() -> Program:
    prog = Program()

    # Shared inputs
    zeros = prog.alloc("zeros", 8)          # [0,0,...,0]
    ones = prog.alloc("ones", 8)            # [1,1,...,1]
    neg_ones = prog.alloc("neg_ones", 8)    # [-1,-1,...,-1]
    input_a = prog.alloc("input_a", 8)      # [1..8]
    neg_a = prog.alloc("neg_a", 8)          # [-1..-8]
    input_b = prog.alloc("input_b", 8)      # [0.5,1.0,...,4.0]
    all_neg = prog.alloc("all_neg", 8)      # [-10..-80]
    all_pos = prog.alloc("all_pos", 8)      # [10..80]
    large_a = prog.alloc("large_a", 8)      # [1e30, ...]
    large_b = prog.alloc("large_b", 8)      # [1e30, ...]
    small_a = prog.alloc("small_a", 8)      # [1e-20, ...]
    small_b = prog.alloc("small_b", 8)      # [1e-20, ...]
    scalar_val = prog.alloc("scalar_val", 1)  # single value for broadcast

    # Register-all inputs (8 separate 8-element vectors)
    reg_d0 = prog.alloc("reg_d0", 8)
    reg_d1 = prog.alloc("reg_d1", 8)
    reg_d2 = prog.alloc("reg_d2", 8)
    reg_d3 = prog.alloc("reg_d3", 8)
    reg_d4 = prog.alloc("reg_d4", 8)
    reg_d5 = prog.alloc("reg_d5", 8)
    reg_d6 = prog.alloc("reg_d6", 8)
    reg_d7 = prog.alloc("reg_d7", 8)

    # Output buffers (one per test)
    out_add_zeros = prog.alloc("out_add_zeros", 8)          # Test 1
    out_mul_zeros = prog.alloc("out_mul_zeros", 8)          # Test 2
    out_add_neg = prog.alloc("out_add_neg", 8)              # Test 3
    out_cancel = prog.alloc("out_cancel", 8)                # Test 4
    out_mul_identity = prog.alloc("out_mul_identity", 8)    # Test 5
    out_add_identity = prog.alloc("out_add_identity", 8)    # Test 6
    out_self_add = prog.alloc("out_self_add", 8)            # Test 7
    out_sub = prog.alloc("out_sub", 8)                      # Test 8
    out_sub_self = prog.alloc("out_sub_self", 8)            # Test 9
    out_relu_pos = prog.alloc("out_relu_pos", 8)            # Test 10
    out_relu_neg = prog.alloc("out_relu_neg", 8)            # Test 11
    out_relu_zero = prog.alloc("out_relu_zero", 8)          # Test 12
    out_chain = prog.alloc("out_chain", 8)                  # Test 13
    out_all_regs = prog.alloc("out_all_regs", 8)            # Test 14
    out_large = prog.alloc("out_large", 8)                  # Test 15
    out_small = prog.alloc("out_small", 8)                  # Test 16
    out_scalar_add = prog.alloc("out_scalar_add", 8)        # Test 17
    out_mul_negone = prog.alloc("out_mul_negone", 8)        # Test 18

    # Kernel calls
    prog.call(add_zeros, A=zeros, B=zeros, C=out_add_zeros)            # 1
    prog.call(mul_zeros, A=zeros, B=zeros, C=out_mul_zeros)            # 2
    prog.call(add_negatives, A=all_neg, B=all_neg, C=out_add_neg)      # 3
    prog.call(add_cancellation, A=input_a, B=neg_a, C=out_cancel)      # 4
    prog.call(mul_identity, A=input_a, Ones=ones, C=out_mul_identity)   # 5
    prog.call(add_identity, A=input_a, Zeros=zeros, C=out_add_identity) # 6
    prog.call(self_add, A=input_a, C=out_self_add)                      # 7
    prog.call(sub_basic, A=input_a, B=input_b, C=out_sub)              # 8
    prog.call(sub_self, A=input_a, C=out_sub_self)                      # 9
    prog.call(relu_all_positive, A=all_pos, C=out_relu_pos)            # 10
    prog.call(relu_all_negative, A=all_neg, C=out_relu_neg)            # 11
    prog.call(relu_zeros, A=zeros, C=out_relu_zero)                     # 12
    prog.call(chain_ops, A=input_a, B=input_b, C=out_chain)            # 13
    prog.call(all_regs,                                                  # 14
              D0=reg_d0, D1=reg_d1, D2=reg_d2, D3=reg_d3,
              D4=reg_d4, D5=reg_d5, D6=reg_d6, D7=reg_d7,
              Out=out_all_regs)
    prog.call(large_values, A=large_a, B=large_b, C=out_large)         # 15
    prog.call(small_values, A=small_a, B=small_b, C=out_small)         # 16
    prog.call(scalar_add_broadcast, A=input_a, S=scalar_val, C=out_scalar_add)  # 17
    prog.call(mul_negone, A=input_a, NegOnes=neg_ones, C=out_mul_negone)        # 18

    return prog


def define_program():
    prog = build_edge_case_program()

    # ------------------------------------------------------------------------
    # Generate Test Data
    # ------------------------------------------------------------------------
    
    # Base arrays
    zeros = np.zeros(8, dtype=np.float32)
    ones = np.ones(8, dtype=np.float32)
    neg_ones = np.full(8, -1.0, dtype=np.float32)
    input_a = np.arange(1, 9, dtype=np.float32)
    neg_a = -input_a
    input_b = np.arange(0.5, 4.5, 0.5, dtype=np.float32)
    all_neg = np.array([-10, -20, -30, -40, -50, -60, -70, -80], dtype=np.float32)
    all_pos = np.array([10, 20, 30, 40, 50, 60, 70, 80], dtype=np.float32)
    large_a = np.array([1e30, 2e30, 3e30, 4e30, 5e30, 6e30, 7e30, 8e30], dtype=np.float32)
    large_b = np.array([1e30, 1e30, 1e30, 1e30, 1e30, 1e30, 1e30, 1e30], dtype=np.float32)
    small_a = np.array([1e-20, 2e-20, 3e-20, 4e-20, 5e-20, 6e-20, 7e-20, 8e-20], dtype=np.float32)
    small_b = np.array([1e-20, 1e-20, 1e-20, 1e-20, 1e-20, 1e-20, 1e-20, 1e-20], dtype=np.float32)
    scalar_val = np.array([100.0], dtype=np.float32) # broadcast value

    inputs = {
        "zeros": zeros,
        "ones": ones,
        "neg_ones": neg_ones,
        "input_a": input_a,
        "neg_a": neg_a,
        "input_b": input_b,
        "all_neg": all_neg,
        "all_pos": all_pos,
        "large_a": large_a,
        "large_b": large_b,
        "small_a": small_a,
        "small_b": small_b,
        "scalar_val": scalar_val,
    }

    # Add reg_d0..d7 inputs for Test 14
    expected_all_regs_sum = np.zeros(8, dtype=np.float32)
    for i in range(8):
        data = np.full(8, float(i + 1), dtype=np.float32)
        inputs[f"reg_d{i}"] = data
        expected_all_regs_sum += data

    # Calculate Expected Outputs
    outputs = {
        "out_add_zeros": zeros + zeros,
        "out_mul_zeros": zeros * zeros,
        "out_add_neg": all_neg + all_neg,
        "out_cancel": input_a + neg_a,
        "out_mul_identity": input_a * ones,
        "out_add_identity": input_a + zeros,
        "out_self_add": input_a + input_a,
        "out_sub": input_a - input_b,
        "out_sub_self": zeros, # result of a-a
        "out_relu_pos": np.maximum(all_pos, 0),
        "out_relu_neg": np.maximum(all_neg, 0),
        "out_relu_zero": np.maximum(zeros, 0),
        "out_chain": (input_a + input_b) * input_a,
        "out_all_regs": expected_all_regs_sum, # V0+V1+...+V7
        "out_large": large_a + large_b,
        "out_small": small_a * small_b,
        "out_scalar_add": input_a + scalar_val[0],
        "out_mul_negone": input_a * neg_ones,
    }

    return prog, inputs, outputs

if __name__ == "__main__":
    from pathlib import Path
    prog, inputs, outputs = define_program()
    harness.save_executable(prog, inputs, outputs, Path("workflow/binaries/simd_edge_cases.npz"))
