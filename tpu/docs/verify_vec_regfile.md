# Verification: vec_regfile.sv

## Scope

This document covers verification coverage for `src/compute_tile/vec_regfile.sv`, extracted from the master verification document.

---

## Role

Vector register file with 8 registers of 8 FP32 lanes each. Dual-port: write port (synchronous, write-enable gated) and two independent read ports. Used by `vpu_simd` to hold intermediate vectors between VLOAD, VCOMPUTE, and VSTORE instructions.

## Test files

- `tpu/verification/compute_tile/test_vec_regfile.py` — 5 dedicated unit tests

## Test functions exercising this module

| Test function | Coverage |
|---|---|
| `test_regfile_reset` | After reset, all registers read as zero |
| `test_regfile_write_read` | Write to each register, read back; all 8 registers |
| `test_regfile_dual_port` | Two simultaneous reads from different registers |
| `test_regfile_all_registers` | Sequential write + read across all 8 register addresses |
| `test_regfile_write_disabled` | Write enable = 0; register value unchanged |

## Coverage details

- All 8 register addresses (0–7) written and read
- Dual read port simultaneous access
- Write enable gating

## Known coverage gaps

- Simultaneous write and read to the same register address (read-during-write behavior)
- FP32 lane isolation: only the first lane is verified in most tests; 8-lane vectors not all asserted
