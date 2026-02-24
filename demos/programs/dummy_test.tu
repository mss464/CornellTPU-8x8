"""
Minimal dummy host script for board hardware verification.
"""
import sys
from pathlib import Path
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from runtime.tuda import host, tudaInit, tudaMalloc, tudaMemcpy, tudaKernelLaunch

@host
def run_dummy():
    print("Starting TUDA Minimal Hardware Test...")
    tudaInit()

    A = np.arange(8, dtype=np.float32)
    B = np.arange(8, dtype=np.float32) * 2
    
    # dummy_add expects A at 0, B at 8, C at 16
    print("\n--- Dummy Vector Add ---")
    tudaMemcpy(0, A, "HostToDevice")
    tudaMemcpy(8, B, "HostToDevice")
    tudaKernelLaunch("binaries/dummy.tpu_bin")
    
    C = tudaMemcpy(16, 8, "DeviceToHost")
    ref_C = A + B
    
    diff = np.max(np.abs(C - ref_C))
    print(f"Max Difference: {diff}")
    
    with open("tuda_result.txt", "w") as f:
        if diff < 1e-3:
            f.write("PASS\n")
            print("Status: PASS")
        else:
            f.write(f"FAIL (Diff: {diff})\n")
            print("Status: FAIL")

if __name__ == "__main__":
    run_dummy()
