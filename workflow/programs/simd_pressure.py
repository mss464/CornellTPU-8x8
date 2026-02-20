#!/usr/bin/env python3
"""
SIMD VPU pressure/performance test program.
"""

import sys
from pathlib import Path
import numpy as np

# Resolve local harness
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import harness

from compiler import Program, kernel, Param

# Scalar kernels (one element per instruction)
@kernel
def scalar_add_32(A: Param, B: Param, C: Param):
    from compiler.instructions import add
    for i in range(32): add(A + i, B + i, C + i)

@kernel
def scalar_mul_32(A: Param, B: Param, C: Param):
    from compiler.instructions import mul
    for i in range(32): mul(A + i, B + i, C + i)

@kernel
def scalar_mlp_32(X: Param, W: Param, Bias: Param, Zero: Param, Y: Param):
    from compiler.instructions import mul, add, relu
    for i in range(32): mul(X + i, W + i, Y + i)
    for i in range(32): add(Y + i, Bias + i, Y + i)
    for i in range(32): relu(Y + i, Zero, Y + i)

# SIMD kernels (8 elements per instruction)
from workflow.kernels.vpu_simd import vector_add_simd, vector_mul_simd, fused_mlp_layer_simd

def build_pressure_programs():
    def alloc_shared(prog):
        layout = {}
        for name, size in [("vec_a_32", 32), ("vec_b_32", 32), ("add_out_32", 32), ("mul_out_32", 32), ("mlp_x", 32), ("mlp_w", 32), ("mlp_bias", 32), ("mlp_out", 32), ("zero", 1)]:
            layout[name] = prog.alloc(name, size)
        return layout

    # Scalar Program
    sprog = Program(); l = alloc_shared(sprog)
    sprog.call(scalar_add_32, A=l["vec_a_32"], B=l["vec_b_32"], C=l["add_out_32"])
    sprog.call(scalar_mul_32, A=l["vec_a_32"], B=l["vec_b_32"], C=l["mul_out_32"])
    sprog.call(scalar_mlp_32, X=l["mlp_x"], W=l["mlp_w"], Bias=l["mlp_bias"], Zero=l["zero"], Y=l["mlp_out"])

    # SIMD Program
    simdprog = Program(); l = alloc_shared(simdprog)
    for chunk in range(4):
        off = chunk * 8
        simdprog.call(vector_add_simd, A=l["vec_a_32"]+off, B=l["vec_b_32"]+off, C=l["add_out_32"]+off)
        simdprog.call(vector_mul_simd, A=l["vec_a_32"]+off, B=l["vec_b_32"]+off, C=l["mul_out_32"]+off)
        simdprog.call(fused_mlp_layer_simd, X=l["mlp_x"]+off, W=l["mlp_w"]+off, Bias=l["mlp_bias"]+off, Y=l["mlp_out"]+off)

    return sprog, simdprog

if __name__ == "__main__":
    s, d = build_pressure_programs()
    # Dummy inputs/outputs for compilation test
    inputs = { "vec_a_32": np.zeros(32, dtype=np.float32), "vec_b_32": np.zeros(32, dtype=np.float32), "mlp_x": np.zeros(32, dtype=np.float32), "mlp_w": np.zeros(32, dtype=np.float32), "mlp_bias": np.zeros(32, dtype=np.float32), "zero": np.zeros(1, dtype=np.float32) }
    harness.save_executable(s, inputs, {}, Path("workflow/binaries/pressure_scalar.npz"))
    harness.save_executable(d, inputs, {}, Path("workflow/binaries/pressure_simd.npz"))
