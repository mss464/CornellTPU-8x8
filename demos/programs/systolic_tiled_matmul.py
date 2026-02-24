#!/usr/bin/env python3
"""
Hardware-fidelity TPU program for 32x32 Tiled Matrix Multiplication.
This script compiles the systolic_matmul kernel and generates a test binary.
"""

import sys
import numpy as np
from pathlib import Path

# Resolve project root and tools
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent.parent.absolute()
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(script_dir.parent / "tools"))

import harness
from compiler import Program
from demos.kernels.systolic_matmul import tiled_matmul_32x32

def define_program():
    prog = Program()
    
    # Dimensions (must be multiples of 32 for this kernel)
    M, N, K = 64, 64, 64
    t = 32
    t2 = t * t
    
    # 1. Allocate Memory
    W_addr = prog.alloc("W", N * K)
    X_addr = prog.alloc("X", M * K)
    Z_addr = prog.alloc("Z", M * N)
    temp_addr = prog.alloc("temp", t2)
    
    # 2. Schedule Kernel Call
    prog.call(tiled_matmul_32x32, W=W_addr, X=X_addr, Z=Z_addr, temp=temp_addr, M=M, N=N, K=K)
    
    # 3. Generate Test Data
    np.random.seed(42)
    X_data = np.random.randn(M, K).astype(np.float32)
    W_data = np.random.randn(N, K).astype(np.float32)
    
    # Note: Hardware MatMul Z = X @ W.T
    Z_expected = X_data @ W_data.T
    
    inputs = {
        "W": W_data.flatten(),
        "X": X_data.flatten(),
    }
    
    outputs = {
        "Z": Z_expected.flatten(),
    }
    
    return prog, inputs, outputs

if __name__ == "__main__":
    prog, inputs, outputs = define_program()
    
    # Conform to the standard style: save to demos/binaries/
    harness.save_executable(
        prog, 
        inputs, 
        outputs, 
        Path("demos/binaries/systolic_tiled_matmul.npz")
    )
    print("✅ Hardware kernel program 'systolic_tiled_matmul' compiled and saved.")
