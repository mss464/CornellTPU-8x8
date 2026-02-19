#!/usr/bin/env python3
"""
SIMD vs Scalar VPU comparison test program.

Run to compile:
    python tests/ultra96-v2/programs/simd_comparison.py

Output:
    tests/ultra96-v2/binaries/simd_comparison.npz
"""

import numpy as np
import harness
from compiler.program import Program
from compiler.kernel import kernel, Param
from compiler.kernels.vpu import vector_add, vector_mul
from compiler.kernels.vpu_simd import (
    vector_add_simd,
    vector_mul_simd,
    vector_relu_simd,
    vector_scale_simd,
    fused_mlp_layer_simd,
)


# ============================================================================
# Scalar baseline kernels (for comparison)
# ============================================================================

@kernel
def vector_add_scalar_8(A: Param, B: Param, C: Param):
    """8-element add using scalar VPU (baseline)."""
    from compiler.tpu_txt import add
    for i in range(8):
        add(A + i, B + i, C + i)


@kernel
def vector_mul_scalar_8(A: Param, B: Param, C: Param):
    """8-element mul using scalar VPU (baseline)."""
    from compiler.tpu_txt import mul
    for i in range(8):
        mul(A + i, B + i, C + i)


# ============================================================================
# Build comparison program
# ============================================================================

def build_simd_comparison_program() -> Program:
    """Build SIMD vs Scalar comparison test program."""
    prog = Program()

    # Test Case 1: Vector Addition (Scalar vs SIMD)
    test_input_a = prog.alloc("test_input_a", 8)
    test_input_b = prog.alloc("test_input_b", 8)
    scalar_add_out = prog.alloc("scalar_add_out", 8)
    simd_add_out = prog.alloc("simd_add_out", 8)

    # Test Case 2: Vector Multiplication (Scalar vs SIMD)
    scalar_mul_out = prog.alloc("scalar_mul_out", 8)
    simd_mul_out = prog.alloc("simd_mul_out", 8)

    # Test Case 3: ReLU (SIMD only)
    relu_input = prog.alloc("relu_input", 8)
    relu_out = prog.alloc("relu_out", 8)

    # Test Case 4: Scalar Broadcast (SIMD only)
    scale_input = prog.alloc("scale_input", 8)
    scale_value = prog.alloc("scale_value", 1)
    scale_out = prog.alloc("scale_out", 8)

    # Test Case 5: Fused MLP Layer (SIMD only)
    mlp_x = prog.alloc("mlp_x", 8)
    mlp_w = prog.alloc("mlp_w", 8)
    mlp_bias = prog.alloc("mlp_bias", 8)
    mlp_out = prog.alloc("mlp_out", 8)

    # Kernel Calls
    prog.call(vector_add_scalar_8, A=test_input_a, B=test_input_b, C=scalar_add_out)
    prog.call(vector_add_simd, A=test_input_a, B=test_input_b, C=simd_add_out)
    prog.call(vector_mul_scalar_8, A=test_input_a, B=test_input_b, C=scalar_mul_out)
    prog.call(vector_mul_simd, A=test_input_a, B=test_input_b, C=simd_mul_out)
    prog.call(vector_relu_simd, X=relu_input, Y=relu_out)
    prog.call(vector_scale_simd, X=scale_input, Scale=scale_value, Y=scale_out)
    prog.call(fused_mlp_layer_simd, X=mlp_x, W=mlp_w, Bias=mlp_bias, Y=mlp_out)

    return prog


def define_program():
    prog = build_simd_comparison_program()

    # ------------------------------------------------------------------------
    # Generate Test Data
    # ------------------------------------------------------------------------
    
    # Test 1 & 2 inputs
    a_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], dtype=np.float32)
    b_data = np.array([0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0], dtype=np.float32)
    
    # Test 3 input
    relu_data = np.array([1.0, -2.0, 3.0, -4.0, 5.0, -6.0, 7.0, -8.0], dtype=np.float32)

    # Test 4 inputs
    scale_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], dtype=np.float32)
    scale_val = np.array([0.5], dtype=np.float32)

    # Test 5 inputs
    mlp_x_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], dtype=np.float32)
    mlp_w_data = np.array([0.5]*8, dtype=np.float32)
    mlp_bias_data = np.array([-1.0, -2.0, -3.0, -4.0, -5.0, -6.0, -7.0, -8.0], dtype=np.float32)

    inputs = {
        "test_input_a": a_data,
        "test_input_b": b_data,
        "relu_input": relu_data,
        "scale_input": scale_data,
        "scale_value": scale_val,
        "mlp_x": mlp_x_data,
        "mlp_w": mlp_w_data,
        "mlp_bias": mlp_bias_data,
    }

    # Calculate Expected Outputs
    outputs = {
        "scalar_add_out": a_data + b_data,
        "simd_add_out": a_data + b_data,
        "scalar_mul_out": a_data * b_data,
        "simd_mul_out": a_data * b_data,
        "relu_out": np.maximum(relu_data, 0),
        "scale_out": scale_data * scale_val[0],
        "mlp_out": np.maximum(mlp_x_data * mlp_w_data + mlp_bias_data, 0)
    }

    return prog, inputs, outputs

if __name__ == "__main__":
    from pathlib import Path
    prog, inputs, outputs = define_program()
    harness.save_executable(prog, inputs, outputs, Path("workflow/binaries/simd_comparison.npz"))
