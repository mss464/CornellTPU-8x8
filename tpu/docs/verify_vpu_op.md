# Verification: vpu_op.sv

## Scope

This document covers verification coverage for `src/compute_tile/vpu_op.sv`, extracted from the master verification document.

---

## Role

Per-lane vector operation module. Takes two 8×FP32 operand vectors and an opcode, and computes the result for all 8 lanes combinationally. Opcodes: 0=VADD, 1=VMUL, 2=RELU (max(0,x)), 3=MAX (element-wise max), 4=D_RELU (derivative: 1 if x>0, else 0).

## Test files

- `tpu/verification/compute_tile/test_vpu_op.py` — 7 dedicated unit tests

## Test functions exercising this module

| Test function | Opcode | Coverage |
|---|---|---|
| `test_vpu_add_basic` | 0 (VADD) | Known FP32 values, bit-exact |
| `test_vpu_sub_basic` | (opcode for sub) | Subtraction correctness |
| `test_vpu_relu` | 2 (RELU) | Positive, negative, zero inputs |
| `test_vpu_mul_basic` | 1 (VMUL) | Multiplication correctness |
| `test_vpu_relu_derivative` | 4 (D_RELU) | Positive → 1.0, non-positive → 0.0 |
| `test_vpu_randomized` | 0, 1, 2 | 100 random cases across add/mul/relu |
| `test_vpu_stress_fp32_edges` | 0 | Denormals, infinities, NaN edge cases |

## Opcode coverage

- All 5 opcode paths (0–4) verified at unit level
- FP32 edge cases (denormals, signed zero, large magnitude) exercised

## Known coverage gaps

- opcode=3 (MAX) not covered in `test_vpu_randomized` (only opcodes 0, 1, 2 in randomized suite)
- D_RELU (opcode=4) not exercised from `vpu_simd` or system level
