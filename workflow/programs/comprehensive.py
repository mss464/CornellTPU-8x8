#!/usr/bin/env python3
"""
Comprehensive test program definition.
"""

import sys
from pathlib import Path
import numpy as np

# Resolve local harness
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import harness

from compiler import Program
from workflow.kernels.matmul import matmul_4x4
from workflow.kernels.vpu_simd import vector_add_simd, vector_relu_simd

def build_comprehensive_program() -> Program:
    prog = Program()

    # VPU SIMD allocations
    a_simd = prog.alloc("a_simd", 8)
    b_simd = prog.alloc("b_simd", 8)
    add_out = prog.alloc("add_out", 8)
    relu_out = prog.alloc("relu_out", 8)

    # 4x4 matmul allocations
    W4 = prog.alloc("W4", 16)
    X4 = prog.alloc("X4", 16)
    Z4 = prog.alloc("Z4", 16)

    # Schedule SIMD operations
    prog.call(vector_add_simd, A=a_simd, B=b_simd, C=add_out)
    prog.call(vector_relu_simd, X=a_simd, Y=relu_out)

    # Schedule 4x4 matmul
    prog.call(matmul_4x4, W=W4, X=X4, Z=Z4)

    return prog

def define_program():
    prog = build_comprehensive_program()

    # Generate Test Data
    np.random.seed(42)
    a_data = np.arange(8, dtype=np.float32)
    b_data = np.arange(8, dtype=np.float32) * 2
    W4 = np.random.randn(4, 4).astype(np.float32)
    X4 = np.random.randn(4, 4).astype(np.float32)

    inputs = {
        "a_simd": a_data,
        "b_simd": b_data,
        "W4": W4.flatten(),
        "X4": X4.flatten(),
    }

    outputs = {
        "add_out": a_data + b_data,
        "relu_out": np.maximum(a_data, 0),
        "Z4": (X4 @ W4.T).flatten(),
    }

    return prog, inputs, outputs

if __name__ == "__main__":
    prog, inputs, outputs = define_program()
    harness.save_executable(prog, inputs, outputs, Path("workflow/binaries/comprehensive.npz"))
