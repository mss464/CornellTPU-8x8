# Verification: systolic.sv

**Role:** Systolic array tile. Instantiates an N×N array of processing elements (`pe.sv`). Each PE implements a multiply-accumulate (MAC) in weight-stationary mode: the weight is held, activations flow horizontally, and partial sums flow vertically.

**Test files:**
- `tpu/verification/compute_tile/test_systolic_array.py` — 1 randomized suite test
- `tpu/verification/compute_tile/test_pe.py` — 4 unit tests for individual PE units
- `tpu/verification/compute_tile/test_mxu.py` — exercised indirectly via MXU controller

**Test functions for systolic array:**

| Test function | Test file | Coverage |
|---|---|---|
| `test_systolic_array_4x4_random_suite` | `test_systolic_array.py` | 100 random 4×4 matmuls; output verified bit-exact to NumPy FP32 |

**100 random case tests:**
- Weight stationary: weight loaded once, activations stream through
- MAC accumulation: multiple partial sums accumulated correctly
- Array flush: all PEs drain after last activation
- Numerical correctness verified against NumPy FP32 reference

**Known coverage gaps:**
- N != 4 systolic array sizes — only 4×4 is tested
- Systolic array with partial zero activations (sparse input)
- Overflow and underflow through the full N×N sum path

**Cross-reference:** See also [verify_pe.md](verify_pe.md) for PE unit tests.
