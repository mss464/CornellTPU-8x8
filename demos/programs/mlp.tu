"""
MLP test utilizing the TUDA host API.
"""
import sys
from pathlib import Path
import numpy as np

# Add project root to path (works locally and deployed)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from runtime.tuda import host, tudaInit, tudaMalloc, tudaMemcpy, tudaKernelLaunch

@host
def run_mlp():
    print("Starting TUDA MLP Test...")
    tudaInit()

    # In Phase 1 static compilation:
    # gemm.tpu_bin expects: W at 0, X at 16, Z at 32
    # relu.tpu_bin expects: X at 0, Y at 16
    
    W1 = np.ones((4, 4), dtype=np.float32) * 0.5
    X0 = np.ones((4, 4), dtype=np.float32)
    W2 = np.ones((4, 4), dtype=np.float32) * 0.5
    
    print("\n--- Layer 1: GEMM ---")
    tudaMemcpy(0, W1, "HostToDevice")
    tudaMemcpy(16, X0, "HostToDevice")
    tudaKernelLaunch("binaries/gemm.tpu_bin")
    Z1 = tudaMemcpy(32, 16, "DeviceToHost").reshape(4,4)
    ref_Z1 = X0 @ W1.T
    
    print("\n--- Layer 2: ReLU ---")
    tudaMemcpy(0, Z1, "HostToDevice")
    tudaKernelLaunch("binaries/relu.tpu_bin")
    A1 = tudaMemcpy(16, 16, "DeviceToHost").reshape(4,4)
    ref_A1 = np.maximum(0, ref_Z1)
    
    print("\n--- Layer 3: GEMM ---")
    tudaMemcpy(0, W2, "HostToDevice")
    tudaMemcpy(16, A1, "HostToDevice")
    tudaKernelLaunch("binaries/gemm.tpu_bin")
    Z2 = tudaMemcpy(32, 16, "DeviceToHost").reshape(4,4)
    ref_Z2 = A1 @ W2.T
    
    # Verify
    diff = np.max(np.abs(Z2 - ref_Z2))
    print(f"Max Difference: {diff}")
    
    with open("tuda_result.txt", "w") as f:
        if diff < 1e-3:
            f.write("PASS\n")
            print("Status: PASS")
        else:
            f.write(f"FAIL (Diff: {diff})\n")
            print("Status: FAIL")

if __name__ == "__main__":
    run_mlp()
