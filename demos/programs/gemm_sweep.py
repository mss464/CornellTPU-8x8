#!/usr/bin/env python3
"""
GEMM Performance Sweep: NumPy vs. TPU Simulator.
Benchmarks the core of the TPU—the 32x32 Systolic Array—against CPU BLAS.
"""

import os
import sys
import time
import numpy as np
from pathlib import Path

# Setup paths relative to script location
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent.parent

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import the simulator
# We add demos/kernels to sys.path
kernels_dir = str(project_root / "demos" / "kernels")
if kernels_dir not in sys.path:
    sys.path.insert(0, kernels_dir)

try:
    import systolic_tiled_matmul
except ImportError as e:
    print(f"Error: Could not find systolic_tiled_matmul in {kernels_dir}: {e}")
    sys.exit(1)

# ANSI Colors for formatted output
BLUE = "\033[94m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
RESET = "\033[0m"

def run_numpy(M, K, N):
    a = np.random.randn(M, K).astype(np.float32)
    b = np.random.randn(K, N).astype(np.float32)
    
    start = time.time()
    _ = a @ b
    end = time.time()
    return (end - start) * 1000

def run_tpu_sim(M, K, N):
    a = np.random.randn(M, K).astype(np.float32)
    b = np.random.randn(K, N).astype(np.float32)
    
    a_flat = a.flatten().tolist()
    b_flat = b.flatten().tolist()
    
    start = time.time()
    c_flat = systolic_tiled_matmul.systolic_tiled_matmul(a_flat, b_flat, M, K, N)
    end = time.time()
    
    # Verification
    c_sim = np.array(c_flat).reshape(M, N)
    c_ref = a @ b
    np.testing.assert_allclose(c_sim, c_ref, rtol=1e-3, atol=1e-3)
    
    return (end - start) * 1000

def main():
    print("\n" + f"{CYAN}{BOLD}═" * 70)
    print(f"🚀  GEMM PERFORMANCE SWEEP: NumPy vs. TPU Simulator (32x32 Tiles)")
    print(f"═" * 70 + RESET)
    print(f"{'Size (MxKxN)':<20} | {'NumPy (ms)':>15} | {'TPU Sim (ms)':>15} | {'Slowdown'}")
    print("-" * 70)

    # Note: 512 is the upper limit for a reasonably fast interactive demo
    sizes = [
        (32, 32, 32),
        (64, 64, 64),
        (128, 128, 128),
        (256, 256, 256),
        (512, 512, 512),
    ]

    for M, K, N in sizes:
        label = f"{M}x{K}x{N}"
        
        # NumPy
        t_np = run_numpy(M, K, N)
        
        # TPU Sim
        try:
            t_sim = run_tpu_sim(M, K, N)
            slowdown = t_sim / t_np
            print(f"{label:<20} | {t_np:>15.4f} | {t_sim:>15.4f} | {slowdown:>8.1f}x")
        except Exception as e:
            print(f"{label:<20} | {t_np:>15.4f} | {'FAILED':>15} | {'-':>8}")
            print(f"  Error: {e}")

    print("-" * 70)
    print(f"{MAGENTA}{BOLD}TPU HW Target:{RESET} [TODO] Deployment to FPGA pending...")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
