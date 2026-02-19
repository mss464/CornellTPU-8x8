#!/usr/bin/env python3
"""
SIMD VPU pressure/performance test program.

Generates TWO programs (scalar baseline and SIMD) that compute identical
workloads, allowing wall-clock timing comparison on the board.

IMPORTANT: Instruction BRAM (blk_mem_gen_1) holds only 256 entries.
All programs MUST fit within 255 instructions + 1 HALT = 256 total.

Run to compile:
    python tests/ultra96-v2/programs/simd_pressure.py

Output:
    tests/ultra96-v2/binaries/pressure_scalar.npz
    tests/ultra96-v2/binaries/pressure_simd.npz
"""

import numpy as np
import harness
from compiler.program import Program
from compiler.kernel import kernel, Param


IRAM_DEPTH = 256  # Hardware limit (8-bit PC)


# ============================================================================
# Scalar kernels (one element per instruction)
# ============================================================================

@kernel
def scalar_add_32(A: Param, B: Param, C: Param):
    """32-element add using scalar VPU: 32 instructions."""
    from compiler.tpu_txt import add
    for i in range(32):
        add(A + i, B + i, C + i)


@kernel
def scalar_mul_32(A: Param, B: Param, C: Param):
    """32-element mul using scalar VPU: 32 instructions."""
    from compiler.tpu_txt import mul
    for i in range(32):
        mul(A + i, B + i, C + i)


@kernel
def scalar_mlp_32(X: Param, W: Param, Bias: Param, Zero: Param, Y: Param):
    """32-element fused MLP: Y = ReLU(X*W + Bias). 96 instructions."""
    from compiler.tpu_txt import mul, add, relu
    for i in range(32):
        mul(X + i, W + i, Y + i)       # Y[i] = X[i] * W[i]
    for i in range(32):
        add(Y + i, Bias + i, Y + i)    # Y[i] = Y[i] + Bias[i]
    for i in range(32):
        relu(Y + i, Zero, Y + i)       # Y[i] = ReLU(Y[i])


@kernel
def scalar_add_64(A: Param, B: Param, C: Param):
    """64-element add using scalar VPU: 64 instructions."""
    from compiler.tpu_txt import add
    for i in range(64):
        add(A + i, B + i, C + i)


# ============================================================================
# SIMD kernels (8 elements per instruction)
# ============================================================================

@kernel
def simd_add_32(A: Param, B: Param, C: Param):
    """32-element add using SIMD VPU: 16 instructions."""
    from compiler.tpu_txt import vload, vadd, vstore
    for chunk in range(4):
        off = chunk * 8
        vload(0, A + off)
        vload(1, B + off)
        vadd(2, 0, 1)
        vstore(2, C + off)


@kernel
def simd_mul_32(A: Param, B: Param, C: Param):
    """32-element mul using SIMD VPU: 16 instructions."""
    from compiler.tpu_txt import vload, vmul, vstore
    for chunk in range(4):
        off = chunk * 8
        vload(0, A + off)
        vload(1, B + off)
        vmul(2, 0, 1)
        vstore(2, C + off)


@kernel
def simd_mlp_32(X: Param, W: Param, Bias: Param, Y: Param):
    """32-element fused MLP: Y = ReLU(X*W + Bias). 28 instructions."""
    from compiler.tpu_txt import vload, vmul, vadd, vrelu, vstore
    for chunk in range(4):
        off = chunk * 8
        vload(0, X + off)
        vload(1, W + off)
        vload(2, Bias + off)
        vmul(3, 0, 1)       # V3 = X * W
        vadd(4, 3, 2)       # V4 = V3 + Bias
        vrelu(5, 4)         # V5 = ReLU(V4)
        vstore(5, Y + off)


@kernel
def simd_add_64(A: Param, B: Param, C: Param):
    """64-element add using SIMD VPU: 32 instructions."""
    from compiler.tpu_txt import vload, vadd, vstore
    for chunk in range(8):
        off = chunk * 8
        vload(0, A + off)
        vload(1, B + off)
        vadd(2, 0, 1)
        vstore(2, C + off)


# ============================================================================
# Build programs
# ============================================================================

def alloc_shared(prog):
    """Allocate shared memory layout. Both programs must call this identically."""
    layout = {}
    layout["vec_a_32"] = prog.alloc("vec_a_32", 32)
    layout["vec_b_32"] = prog.alloc("vec_b_32", 32)
    layout["add_out_32"] = prog.alloc("add_out_32", 32)
    layout["mul_out_32"] = prog.alloc("mul_out_32", 32)
    layout["mlp_x"] = prog.alloc("mlp_x", 32)
    layout["mlp_w"] = prog.alloc("mlp_w", 32)
    layout["mlp_bias"] = prog.alloc("mlp_bias", 32)
    layout["mlp_out"] = prog.alloc("mlp_out", 32)
    layout["zero"] = prog.alloc("zero", 1)
    layout["vec_a_64"] = prog.alloc("vec_a_64", 64)
    layout["vec_b_64"] = prog.alloc("vec_b_64", 64)
    layout["add_out_64"] = prog.alloc("add_out_64", 64)
    return layout


def build_scalar_program() -> Program:
    prog = Program()
    l = alloc_shared(prog)

    prog.call(scalar_add_32, A=l["vec_a_32"], B=l["vec_b_32"], C=l["add_out_32"])
    prog.call(scalar_mul_32, A=l["vec_a_32"], B=l["vec_b_32"], C=l["mul_out_32"])
    prog.call(scalar_mlp_32, X=l["mlp_x"], W=l["mlp_w"], Bias=l["mlp_bias"],
              Zero=l["zero"], Y=l["mlp_out"])
    prog.call(scalar_add_64, A=l["vec_a_64"], B=l["vec_b_64"], C=l["add_out_64"])

    return prog


def build_simd_program() -> Program:
    prog = Program()
    l = alloc_shared(prog)

    prog.call(simd_add_32, A=l["vec_a_32"], B=l["vec_b_32"], C=l["add_out_32"])
    prog.call(simd_mul_32, A=l["vec_a_32"], B=l["vec_b_32"], C=l["mul_out_32"])
    prog.call(simd_mlp_32, X=l["mlp_x"], W=l["mlp_w"], Bias=l["mlp_bias"],
              Y=l["mlp_out"])
    prog.call(simd_add_64, A=l["vec_a_64"], B=l["vec_b_64"], C=l["add_out_64"])

    return prog


def define_programs():
    # ------------------------------------------------------------------------
    # Generate Shared Test Data
    # ------------------------------------------------------------------------
    np.random.seed(42)

    vec_a_32 = np.random.uniform(0, 10, 32).astype(np.float32)
    vec_b_32 = np.random.uniform(0, 10, 32).astype(np.float32)
    mlp_x = np.random.uniform(-5, 5, 32).astype(np.float32)
    mlp_w = np.random.uniform(-1, 1, 32).astype(np.float32)
    mlp_bias = np.random.uniform(-2, 2, 32).astype(np.float32)
    zero = np.array([0.0], dtype=np.float32)
    vec_a_64 = np.random.uniform(0, 10, 64).astype(np.float32)
    vec_b_64 = np.random.uniform(0, 10, 64).astype(np.float32)

    inputs = {
        "vec_a_32": vec_a_32,
        "vec_b_32": vec_b_32,
        "mlp_x": mlp_x,
        "mlp_w": mlp_w,
        "mlp_bias": mlp_bias,
        "zero": zero,
        "vec_a_64": vec_a_64,
        "vec_b_64": vec_b_64,
    }

    # Calculate Expected Outputs
    outputs = {
        "add_out_32": vec_a_32 + vec_b_32,
        "mul_out_32": vec_a_32 * vec_b_32,
        "mlp_out": np.maximum(mlp_x * mlp_w + mlp_bias, 0),
        "add_out_64": vec_a_64 + vec_b_64,
    }

    # ------------------------------------------------------------------------
    # Build Programs
    # ------------------------------------------------------------------------
    scalar_prog = build_scalar_program()
    simd_prog = build_simd_program()

    return {
        "pressure_scalar": (scalar_prog, inputs, outputs),
        "pressure_simd": (simd_prog, inputs, outputs)
    }

if __name__ == "__main__":
    from pathlib import Path
    programs = define_programs()
    for name, (prog, inputs, outputs) in programs.items():
        harness.save_executable(prog, inputs, outputs, Path(f"workflow/binaries/{name}.npz"))
