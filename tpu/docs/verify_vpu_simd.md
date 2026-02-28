# Verification: vpu_simd.sv

## Scope

This document covers verification coverage for `src/compute_tile/vpu_simd.sv`, extracted from the master verification document.

---

## Role

SIMD vector processing unit. Implements VLOAD (read 8 FP32 words from L1 into a vector register), VSTORE (write vector register to L1), VCOMPUTE (arithmetic on two vector registers), and SCALAR (broadcast scalar from L1 to one operand). FSM states: `IDLE`, VLOAD states (`VLOAD_REQ`, `VLOAD_WAIT`, `VLOAD_LATCH`), VSTORE states (`VSTORE_REQ`, `VSTORE_WRITE`), `VCOMPUTE`, `SCALAR_READ_A`, `SCALAR_WAIT_A`, `SCALAR_LATCH_A`, `SCALAR_WAIT_B`, `SCALAR_COMPUTE`, `DONE_STATE`.

## Test files

- `tpu/verification/compute_tile/test_vpu_simd.py` — 10 dedicated unit tests

## Test functions exercising this module

| Test function | Test file | vpu_type / opcode |
|---|---|---|
| `test_vpu_simd_reset` | `test_vpu_simd.py` | Reset → IDLE, output signals cleared |
| `test_vcompute_simple` | `test_vpu_simd.py` | VCOMPUTE (type=3), VADD (opcode=0), zero registers |
| `test_vload_sequential` | `test_vpu_simd.py` | VLOAD (type=1) from BRAM, sequential addresses |
| `test_vstore_sequential` | `test_vpu_simd.py` | VSTORE (type=2) to BRAM, sequential addresses |
| `test_vcompute_scalar_broadcast` | `test_vpu_simd.py` | Scalar broadcast path (scalar_b=1), timing |
| `test_invalid_vpu_type` | `test_vpu_simd.py` | vpu_type=0 (no-op), FSM does not stall |
| `test_vpu_simd_data_correctness` | `test_vpu_simd.py` | VLOAD + VADD + VSTORE with FP32 bit-exact verification |
| `test_scalar_add` | `test_vpu_simd.py` | SCALAR path: scalar_b=1, VADD with scalar |
| `test_scalar_relu` | `test_vpu_simd.py` | SCALAR path: scalar_b=1, RELU with scalar |
| `test_scalar_mul` | `test_vpu_simd.py` | SCALAR path: scalar_b=1, VMUL with scalar |

## FSM states

- `IDLE` — reset state, start signal transitions to active state
- VLOAD path: `VLOAD_REQ` (BRAM address issued), `VLOAD_WAIT` (1-cycle BRAM latency), `VLOAD_LATCH` (data captured into vector register)
- VSTORE path: `VSTORE_REQ` (vector register data driven), `VSTORE_WRITE` (BRAM wea asserted)
- `VCOMPUTE` — `vpu_op` sub-module computes result per lane
- SCALAR path: `SCALAR_READ_A` (issue L1 read for scalar), `SCALAR_WAIT_A` (BRAM latency), `SCALAR_LATCH_A` (latch scalar), `SCALAR_WAIT_B` (second BRAM read if needed), `SCALAR_COMPUTE` (broadcast and compute)
- `DONE_STATE` — done pulse, return to IDLE

## Known coverage gaps

- `test_vcompute_scalar_broadcast`: timing only verified, not data values of scalar broadcast result
- VMUL (`vpu_opcode=1`) and D_RELU (`vpu_opcode=4`) not exercised in system-level kernel
- VCOMPUTE with MAX opcode (`vpu_opcode=3`) not tested in `test_vpu_simd.py`
- Multi-register programs (accumulating into vreg 3–7) not tested; only vreg 0, 1, 2 used
