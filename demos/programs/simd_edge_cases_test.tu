"""
SIMD VPU corner/edge case test runner utilizing TUDA API.
"""
import sys
from pathlib import Path
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.tuda import host, tudaInit, tudaMemcpy, tudaKernelLaunch

# Known memory map from static compilation
MEM_MAP = {
    'zeros': 0, 'ones': 8, 'neg_ones': 16, 'input_a': 24, 'neg_a': 32, 'input_b': 40,
    'all_neg': 48, 'all_pos': 56, 'large_a': 64, 'large_b': 72, 'small_a': 80, 'small_b': 88,
    'scalar_val': 96,
    'reg_d0': 97, 'reg_d1': 105, 'reg_d2': 113, 'reg_d3': 121, 'reg_d4': 129, 'reg_d5': 137, 'reg_d6': 145, 'reg_d7': 153,
    'out_add_zeros': 161, 'out_mul_zeros': 169, 'out_add_neg': 177, 'out_cancel': 185, 'out_mul_id': 193, 'out_add_id': 201, 'out_self_add': 209, 'out_sub': 217, 'out_sub_self': 225, 'out_relu_pos': 233, 'out_relu_neg': 241, 'out_relu_zero': 249, 'out_chain': 257, 'out_all_regs': 265, 'out_large': 273, 'out_small': 281, 'out_scalar_add': 289, 'out_mul_negone': 297
}

@host
def run_simd_edge_cases():
    print("Starting TUDA SIMD Edge Cases Test...")
    tudaInit()

    a_data = np.arange(1, 9, dtype=np.float32)
    inputs = { 
        "zeros": np.zeros(8, dtype=np.float32), 
        "ones": np.ones(8, dtype=np.float32), 
        "neg_ones": np.full(8, -1.0, dtype=np.float32), 
        "input_a": a_data, 
        "neg_a": -a_data, 
        "input_b": np.arange(0.5, 4.5, 0.5, dtype=np.float32), 
        "all_neg": -10*a_data, 
        "all_pos": 10*a_data, 
        "large_a": 1e30*np.ones(8, dtype=np.float32), 
        "large_b": 1e30*np.ones(8, dtype=np.float32), 
        "small_a": 1e-20*np.ones(8, dtype=np.float32), 
        "small_b": 1e-20*np.ones(8, dtype=np.float32), 
        "scalar_val": np.array([100.0], dtype=np.float32) 
    }
    for i in range(8): inputs[f"reg_d{i}"] = np.full(8, float(i+1), dtype=np.float32)

    # Calculate expected
    expected = {
        "out_add_zeros": np.zeros(8, dtype=np.float32),
        "out_mul_zeros": np.zeros(8, dtype=np.float32),
        "out_add_neg": inputs["all_neg"] + inputs["all_neg"],
        "out_cancel": np.zeros(8, dtype=np.float32),
        "out_mul_id": inputs["input_a"],
        "out_add_id": inputs["input_a"],
        "out_self_add": inputs["input_a"] + inputs["input_a"],
        "out_sub": inputs["input_a"] - inputs["input_b"],
        "out_sub_self": np.zeros(8, dtype=np.float32),
        "out_relu_pos": np.maximum(inputs["all_pos"], 0),
        "out_relu_neg": np.zeros(8, dtype=np.float32),
        "out_relu_zero": np.zeros(8, dtype=np.float32),
        "out_chain": (inputs["input_a"] + inputs["input_b"]) * inputs["input_a"],
        "out_all_regs": sum(inputs[f"reg_d{i}"] for i in range(8)),
        "out_large": inputs["large_a"] + inputs["large_b"],
        "out_small": inputs["small_a"] * inputs["small_b"],
        "out_scalar_add": inputs["input_a"] + inputs["scalar_val"][0],
        "out_mul_negone": inputs["input_a"] * -1.0
    }

    print("\n--- Writing Inputs ---")
    for name, data in inputs.items():
        if name in MEM_MAP:
            tudaMemcpy(MEM_MAP[name], np.asarray(data).flatten().astype(np.float32), "HostToDevice")

    print("\n--- Launching Kernel ---")
    tudaKernelLaunch("binaries/simd_edge_cases.tpu_bin")

    print("\n--- Reading back Outputs ---")
    all_pass = True
    for name, exp_data in expected.items():
        addr = MEM_MAP[name]
        actual = tudaMemcpy(addr, exp_data.size, "DeviceToHost").reshape(exp_data.shape)
        
        if np.allclose(actual, exp_data, rtol=1e-3, atol=1e-3):
            print(f"  {name:<15}: PASS")
        else:
            diff = np.max(np.abs(actual - exp_data))
            print(f"  {name:<15}: FAIL (Max diff: {diff:.6f})")
            all_pass = False

    if all_pass:
        print("\nResult: SUCCESS")
        sys.exit(0)
    else:
        print("\nResult: FAILURE")
        sys.exit(1)

if __name__ == "__main__":
    run_simd_edge_cases()
