#!/usr/bin/env python3
"""
Comprehensive test program definition.

Defines what kernels to run and memory layout. Run to compile:
    python tests/ultra96-v2/programs/comprehensive.py

Output:
    tests/ultra96-v2/binaries/comprehensive.npz
"""

import sys
from pathlib import Path
import numpy as np
import harness
from compiler.program import Program
from compiler.kernel import kernel, Param
from compiler.kernels.matmul import matmul_4x4, matmul_8x8_tiled


# ============================================================================
# Define VPU test kernels
# ============================================================================

@kernel
def vpu_add_n(A: Param, B: Param, C: Param, n: int = 4):
    from compiler.tpu_txt import add
    for i in range(n):
        add(A + i, B + i, C + i)


@kernel
def vpu_sub_n(A: Param, B: Param, C: Param, n: int = 4):
    from compiler.tpu_txt import sub
    for i in range(n):
        sub(A + i, B + i, C + i)


@kernel
def vpu_mul_n(A: Param, B: Param, C: Param, n: int = 4):
    from compiler.tpu_txt import mul
    for i in range(n):
        mul(A + i, B + i, C + i)


@kernel
def vpu_relu_n(X: Param, Zero: Param, Y: Param, n: int = 4):
    from compiler.tpu_txt import relu
    for i in range(n):
        relu(X + i, Zero, Y + i)


# ============================================================================
# Build program
# ============================================================================

def build_comprehensive_program() -> Program:
    """Build the comprehensive test program."""
    prog = Program()

    # VPU test allocations
    a = prog.alloc("a", 4)
    b = prog.alloc("b", 4)
    zero = prog.alloc("zero", 1)
    add_out = prog.alloc("add_out", 4)
    sub_out = prog.alloc("sub_out", 4)
    mul_out = prog.alloc("mul_out", 4)
    relu_out = prog.alloc("relu_out", 4)

    # 4x4 matmul allocations
    W4 = prog.alloc("W4", 16)
    X4 = prog.alloc("X4", 16)
    Z4 = prog.alloc("Z4", 16)

    # 8x8 tiled matmul allocations (tile-major layout)
    W8 = prog.alloc("W8", 64)
    X8 = prog.alloc("X8", 64)
    Z8 = prog.alloc("Z8", 64)
    temp = prog.alloc("temp", 16)

    # Schedule VPU operations
    prog.call(vpu_add_n, A=a, B=b, C=add_out)
    prog.call(vpu_sub_n, A=a, B=b, C=sub_out)
    prog.call(vpu_mul_n, A=a, B=b, C=mul_out)
    prog.call(vpu_relu_n, X=a, Zero=zero, Y=relu_out)

    # Schedule 4x4 matmul
    prog.call(matmul_4x4, W=W4, X=X4, Z=Z4)

    # Schedule 8x8 tiled matmul
    prog.call(matmul_8x8_tiled, W=W8, X=X8, Z=Z8, temp=temp)

    return prog


def define_program():
    prog = build_comprehensive_program()

    # ------------------------------------------------------------------------
    # Generate Test Data
    # ------------------------------------------------------------------------
    np.random.seed(42)

    # VPU Inputs
    a = np.array([1.5, -2.0, 3.0, -0.5], dtype=np.float32)
    b = np.array([0.5, 1.0, -1.0, 2.0], dtype=np.float32)
    zero = np.array([0.0], dtype=np.float32)
    
    # Matmul Inputs
    W4 = np.random.randn(4, 4).astype(np.float32)
    X4 = np.random.randn(4, 4).astype(np.float32)
    X8 = np.random.randn(8, 8).astype(np.float32)
    W8 = np.random.randn(8, 8).astype(np.float32)

    # Calculate Expected Outputs
    expected_vpu_add = a + b
    expected_vpu_sub = a - b
    expected_vpu_mul = a * b
    expected_vpu_relu = np.maximum(a, 0)
    expected_matmul4 = X4 @ W4.T
    expected_matmul8 = X8 @ W8.T

    # ------------------------------------------------------------------------
    # Define Inputs and Outputs
    # ------------------------------------------------------------------------
    inputs = {
        "a": a,
        "b": b,
        "zero": zero,
        "W4": W4.flatten(),
        "X4": X4.flatten(),
        "W8": harness.to_tile_major(W8, 4),
        "X8": harness.to_tile_major(X8, 4),
        "Z8": np.zeros(64, dtype=np.float32),
    }

    outputs = {
        "add_out": expected_vpu_add,
        "sub_out": expected_vpu_sub,
        "mul_out": expected_vpu_mul,
        "relu_out": expected_vpu_relu,
        "Z4": expected_matmul4.flatten(),
        "Z8": harness.to_tile_major(expected_matmul8, 4),
    }

    return prog, inputs, outputs

if __name__ == "__main__":
    # Allow running directly for backward compatibility or quick testing
    prog, inputs, outputs = define_program()
    harness.save_executable(prog, inputs, outputs, Path("workflow/binaries/comprehensive.npz"))
