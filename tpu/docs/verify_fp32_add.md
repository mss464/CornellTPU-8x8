# Verification: fp32_add.sv

## Scope

This document covers verification coverage for `src/compute_tile/fp32_add.sv`, extracted from the master verification document.

---

## Role

IEEE-754 single-precision FP32 adder. Purely combinational block used by `pe.sv` (MAC) and `vpu_op.sv` (per-lane operations).

## Test files

- `tpu/verification/compute_tile/test_fp32_add.py` — 1 test function (vector of cases)
- Exercised indirectly by: `test_pe.py`, `test_vpu_op.py`, `test_vpu_simd.py`, `test_systolic_array.py`

## Test functions exercising this module

| Test function | Test file | Coverage |
|---|---|---|
| `test_fp32_add_vectors` | `test_fp32_add.py` | Vector of known FP32 pairs; result bit-exact vs Python |

## Behavioral paths covered

- Normal FP32 addition across a range of magnitudes and signs
- Bit-exact comparison to Python `struct.pack` reference

## Known coverage gaps

- Subnormal (denormal) inputs not isolated in unit tests (covered partially in `test_vpu_stress_fp32_edges`)
- Overflow (result exceeds FP32 max) not tested at `fp32_add` unit level
- NaN and infinity propagation not tested at unit level
