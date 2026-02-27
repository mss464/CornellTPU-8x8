"""
Comprehensive test utilizing the TUDA host API.
"""
import sys
from pathlib import Path
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.tuda import host, tudaInit, tudaMemcpy, tudaKernelLaunch

@host
def run_comprehensive():
    print("Starting TUDA Comprehensive Test...")
    tudaInit()

    # Memory Map matches comprehensive.tu compilation:
    # a_simd: 0, b_simd: 8, add_out: 16, relu_out: 24, W4: 32, X4: 48, Z4: 64
    
    # Generate Test Data
    np.random.seed(42)
    a_data = np.arange(8, dtype=np.float32)
    b_data = np.arange(8, dtype=np.float32) * 2
    W4 = np.random.randn(4, 4).astype(np.float32)
    X4 = np.random.randn(4, 4).astype(np.float32)

    # Expected Outputs
    ref_add = a_data + b_data
    ref_relu = np.maximum(a_data, 0)
    ref_Z4 = X4 @ W4.T

    print("\n--- Writing Inputs ---")
    tudaMemcpy(0, a_data, "HostToDevice")
    tudaMemcpy(8, b_data, "HostToDevice")
    tudaMemcpy(32, W4.flatten(), "HostToDevice")
    tudaMemcpy(48, X4.flatten(), "HostToDevice")

    print("\n--- Launching Kernel ---")
    tudaKernelLaunch("binaries/comprehensive.tpu_bin")

    print("\n--- Reading back Outputs ---")
    out_add = tudaMemcpy(16, 8, "DeviceToHost")
    out_relu = tudaMemcpy(24, 8, "DeviceToHost")
    out_Z4 = tudaMemcpy(64, 16, "DeviceToHost").reshape(4, 4)

    all_pass = True
    
    def check(name, actual, expected):
        nonlocal all_pass
        diff = np.max(np.abs(actual - expected))
        if diff < 1e-3:
            print(f"  {name:<10}: PASS")
        else:
            print(f"  {name:<10}: FAIL (Max diff: {diff:.6f})")
            all_pass = False

    check("add_out", out_add, ref_add)
    check("relu_out", out_relu, ref_relu)
    check("Z4", out_Z4, ref_Z4)

    with open("tuda_result.txt", "w") as f:
        if all_pass:
            f.write("PASS\n")
            print("\nStatus: SUCCESS")
            sys.exit(0)
        else:
            f.write("FAIL\n")
            print("\nStatus: FAILURE")
            sys.exit(1)

if __name__ == "__main__":
    run_comprehensive()
