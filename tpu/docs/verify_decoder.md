# Verification: decoder.sv

**Role:** 64-bit ISA instruction decoder. Combinationally decodes the instruction word fetched from IRAM and drives `mode`, `addr_a`, `addr_b`, `addr_out`, `vpu_type`, `vreg_dst`, `vreg_a`, `vreg_b`, `vpu_opcode`, `scalar_b` output signals to the tensorcore FSM. Hardware field layout: `[63:62]=mode`, `[61:49]=addr_a`, `[48:36]=addr_b`, `[35:23]=addr_out`, `[22:20]=vpu_type`, `[19:17]=vreg_dst`, `[16:14]=vreg_a`, `[13:11]=vreg_b`, `[6:4]=vpu_opcode`, `[3]=scalar_b`.

**Test files:**
- `tpu/verification/compute_tile/test_decoder.py` — 6 unit tests for the hardware field layout
- `tpu/verification/compute_tile/test_isa_decoder.py` — 4 tests for the compiler-facing 4-bit type field
- All compute tests exercise decoder indirectly through tensorcore

**Test functions exercising this module:**

| Test function | Test file | Coverage |
|---|---|---|
| `test_decoder_zero_instruction` | `test_decoder.py` | All-zero input; all outputs = 0 |
| `test_decoder_max_values` | `test_decoder.py` | All-ones input; field saturation |
| `test_decoder_mode_field` | `test_decoder.py` | mode=0 (VPU), mode=1 (MXU), mode=3 (HALT) — bit patterns |
| `test_decoder_address_fields` | `test_decoder.py` | addr_a, addr_b, addr_out field isolation |
| `test_decoder_randomized` | `test_decoder.py` | Randomized field packing/unpacking |
| `test_decoder_typical_instructions` | `test_decoder.py` | Typical VLOAD, VSTORE, HALT, MATMUL encodings |
| `test_vpu_simd_add_instruction` | `test_isa_decoder.py` | Compiler 4-bit type; VPU ADD encoding |
| `test_systolic_instruction` | `test_isa_decoder.py` | Compiler 4-bit type; MXU encoding |
| `test_halt_instruction` | `test_isa_decoder.py` | Compiler 4-bit type; HALT encoding |
| `test_full_address_range` | `test_isa_decoder.py` | Compiler 4-bit type; full address field range |

**Decoder field coverage:**
- `mode` = 0 (VPU): `test_decoder_mode_field`, all VPU tests
- `mode` = 1 (MXU): `test_decoder_mode_field`, `test_systolic_instruction`
- `mode` = 2 (TMA): exercised by `test_tma_instruction_in_kernel` (instruction encoded in test, decoded in RTL)
- `mode` = 3 (HALT): `test_decoder_mode_field`, `test_tensorcore_halt`
- `vpu_type` = 1 (VLOAD): `test_tensorcore_vload_vhalt`, `test_compute_identity_kernel`
- `vpu_type` = 2 (VSTORE): `test_tensorcore_vpu_data_flow`, `test_compute_identity_kernel`
- `vpu_type` = 3 (VCOMPUTE): `test_vcompute_simple`, `test_compute_vadd_kernel`
- `vpu_opcode` = 0 (VADD): `test_compute_vadd_kernel`, `test_vpu_simd_add_instruction`
- `scalar_b` = 1: `test_scalar_add`, `test_scalar_relu`, `test_scalar_mul` (vpu_simd unit)

**Known coverage gaps:**
- `vpu_opcode` = 2 (VMUL) and `vpu_opcode` = 4 (D_RELU) not exercised from system-level decoder decode — only unit-level `test_vpu_op.py`
- TMA sub-fields `[61]=dir`, `[60:45]=dm_base`, `[44:30]=l2_base`, `[29:14]=length` not verified with explicit decoder unit test (exercised indirectly)
- ISA layout discrepancy: hardware uses `[63:62]` for mode (2-bit); compiler uses `[63:60]` for type (4-bit). Both are valid within their domains; `test_decoder.py` covers hardware, `test_isa_decoder.py` covers compiler. No integration test bridges both.
