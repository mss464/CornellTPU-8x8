# Verification: pe.sv

**Role:** Single processing element (MAC). Part of `systolic.sv` N×N array. Each PE implements a multiply-accumulate (MAC) in weight-stationary mode: the weight is held, activations flow horizontally, and partial sums flow vertically. `pe.sv` produces `pe_out = activation_in * weight + sum_in` using `fp32_mul` + `fp32_add`.

**Test files:**
- `tpu/verification/compute_tile/test_pe.py` — 4 unit tests for a single PE
- `tpu/verification/compute_tile/test_systolic_array.py` — 1 randomized suite test
- `tpu/verification/compute_tile/test_mxu.py` — exercised indirectly via MXU controller

**Test functions exercising this module:**

| Test function | Test file | Coverage |
|---|---|---|
| `test_pe` | `test_pe.py` | Basic MAC: `out = a*w + sum` |
| `test_pe_fp32_extremes_and_signs` | `test_pe.py` | Very large/small values, sign combinations |
| `test_pe_back_to_back_valid` | `test_pe.py` | Valid high for multiple consecutive cycles |
| `test_pe_enable_disable` | `test_pe.py` | PE enable/disable; output freezes when disabled |
| `test_systolic_array_4x4_random_suite` | `test_systolic_array.py` | 100 random 4×4 matmuls; output verified bit-exact to NumPy FP32 |

**Coverage details:**
- Weight stationary: weight loaded once, activations stream through
- MAC accumulation: multiple partial sums accumulated correctly
- Array flush: all PEs drain after last activation
- 100 random test cases verify numerical correctness
