# Verification: mxu.sv

**Role:** Matrix unit controller. Reads weight matrix (W) and activation matrix (X) from L1 BRAM Port B, feeds them into the systolic array, and writes the output matrix to L1. FSM states: `IDLE`, `START`, `INIT_COUNTER`, `MATMUL_WAIT`, `WRITE_DONE`.

**Test files:**
- `tpu/verification/compute_tile/test_mxu.py` — 7 dedicated unit tests

**Test functions exercising this module:**

| Test function | Coverage |
|---|---|
| `test_sequential_matmul_no_reset` | Two back-to-back matmuls without reset between them |
| `test_alternating_weight_patterns` | Alternating W matrices with same X; output correctness |
| `test_multiple_sequential_random` | Multiple sequential random 4×4 matmuls |
| `test_fp32_extremes` | Very large and very small FP32 values as inputs |
| `test_back_to_back_start` | `start` pulsed immediately after previous done; re-entrancy |
| `test_row_column_boundary` | Edge case at matrix dimension boundary (N=4) |
| `test_base_addr_aliasing_writeback` | Output base address (`BASE_ADDR_OUT`) aliasing verification |

**FSM states covered:**
- `IDLE` — entry after reset; re-entry after each matmul
- `START` — registered `start` pulse; BRAM read initiated
- `INIT_COUNTER` — prefetching W and X from L1 BRAM
- `MATMUL_WAIT` — systolic array computing; waiting for internal done
- `WRITE_DONE` — writing systolic output back to L1 BRAM

**Known coverage gaps:**
- `MEM_LATENCY=1` parameter path: only `test_fp32_extremes` implicitly tests timing; no explicit latency sweep
- Matmul correctness assertion (expected == actual output matrix): `test_mxu.py` tests measure completion but the comment in the original verification doc noted correctness was not verified — `test_multiple_sequential_random` and `test_alternating_weight_patterns` do verify output via the memory model writeback
- System-level MXU matmul kernel: no system test dispatches a MODE=1 MXU instruction; MXU is only tested at unit level
