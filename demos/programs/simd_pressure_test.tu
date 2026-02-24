"""
SIMD VPU pressure/performance test program.
"""
import sys
import time
from pathlib import Path
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.tuda import host, tudaInit, tudaMemcpy, tudaKernelLaunch

# Known memory map from static compilation (same for both scalar and simd programs)
MEM_MAP = {
    'vec_a_32': 0, 'vec_b_32': 32, 'add_out_32': 64, 'mul_out_32': 96,
    'mlp_x': 128, 'mlp_w': 160, 'mlp_bias': 192, 'mlp_out': 224, 'zero': 256
}

def get_inputs():
    np.random.seed(42)
    return {
        "vec_a_32": np.random.randn(32).astype(np.float32),
        "vec_b_32": np.random.randn(32).astype(np.float32),
        "mlp_x": np.random.randn(32).astype(np.float32),
        "mlp_w": np.random.randn(32).astype(np.float32),
        "mlp_bias": np.random.randn(32).astype(np.float32),
        "zero": np.zeros(1, dtype=np.float32)
    }

@host
def run_pressure(bin_path, use_simd):
    print(f"Starting Pressure Test ({'SIMD' if use_simd else 'SCALAR'})...")
    tudaInit()
    
    inputs = get_inputs()

    # Write inputs
    for name, data in inputs.items():
        if name in MEM_MAP:
            tudaMemcpy(MEM_MAP[name], data, "HostToDevice")

    print(f"Launching core binary: {bin_path}")
    start_t = time.perf_counter()
    tudaKernelLaunch(str(bin_path))
    end_t = time.perf_counter()
    
    duration = end_t - start_t
    print(f"Execution time: {duration*1000:.3f} ms")

    # Verification
    out_add = tudaMemcpy(MEM_MAP["add_out_32"], 32, "DeviceToHost")
    ref_add = inputs["vec_a_32"] + inputs["vec_b_32"]
    
    diff = np.max(np.abs(out_add - ref_add))
    if diff < 1e-3:
        print("Result: SUCCESS")
        return True
    else:
        print(f"Result: FAILURE (Max diff from ADD: {diff:.6f})")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["scalar", "simd", "both"], default="both", help="Which variant to run")
    args = parser.parse_args()

    binaries_dir = Path(__file__).resolve().parent.parent / "binaries"
    scalar_bin = binaries_dir / "pressure_scalar.tpu_bin"
    simd_bin = binaries_dir / "pressure_simd.tpu_bin"
        
    all_pass = True
    if args.mode in ["scalar", "both"]:
        if not scalar_bin.exists():
            print(f"Error: {scalar_bin} not found.")
            sys.exit(1)
        print("\n--- Scalar Run ---")
        if not run_pressure(scalar_bin, use_simd=False): all_pass = False
        
    if args.mode in ["simd", "both"]:
        if not simd_bin.exists():
            print(f"Error: {simd_bin} not found.")
            sys.exit(1)
        print("\n--- SIMD Run ---")
        if not run_pressure(simd_bin, use_simd=True): all_pass = False

    if not all_pass:
        sys.exit(1)
