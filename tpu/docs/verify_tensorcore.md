# Verification: tensorcore.sv

## Scope

This document covers verification coverage for `src/compute_tile/tensorcore.sv` and its closely related modules `compute_tile.sv` and `l1.sv`, extracted from the master verification document.

---

## Role

Instruction fetch and dispatch FSM. Fetches 64-bit instructions from IRAM (`blk_mem_gen_1`) using the program counter (`pc`), decodes via `decoder.sv`, and dispatches to MXU, VPU, or TMA engines. FSM states: `FETCH` (wait for IRAM read latency), `IDLE` (decode and dispatch), `MXU_EXEC`, `MXU_WAIT`, `VPU_EXEC`, `VPU_WAIT`, `TMA_EXEC`, `TMA_WAIT`, `HALT`.

## Test files

- `tpu/verification/compute_tile/test_tensorcore.py` — 3 unit tests
- `tpu/verification/system/test_tpu_compute.py` — all 4 system compute tests exercise tensorcore

## Test functions exercising this module

| Test function | Test file | States visited |
|---|---|---|
| `test_tensorcore_halt` | `test_tensorcore.py` | FETCH → IDLE → HALT |
| `test_tensorcore_vload_vhalt` | `test_tensorcore.py` | FETCH → IDLE → VPU_EXEC → VPU_WAIT → FETCH → IDLE → HALT |
| `test_tensorcore_vpu_data_flow` | `test_tensorcore.py` | FETCH → IDLE → VPU_EXEC → VPU_WAIT (×2) → HALT |
| `test_compute_identity_kernel` | `test_tpu_compute.py` | VPU_EXEC/WAIT → VPU_EXEC/WAIT → HALT |
| `test_compute_vadd_kernel` | `test_tpu_compute.py` | VPU_EXEC/WAIT (×4) → HALT |
| `test_tma_instruction_in_kernel` | `test_tpu_compute.py` | TMA_EXEC → TMA_WAIT → HALT |
| `test_dma_compute_overlap` | `test_tpu_compute.py` | VPU_EXEC/WAIT (×2) → HALT |

## FSM states

- `FETCH` — IRAM read issued, 1-cycle latency wait
- `IDLE` — instruction decoded, dispatch decision made
- `VPU_EXEC` — `vpu_start` asserted; entered for VLOAD, VSTORE, VCOMPUTE instructions
- `VPU_WAIT` — wait for `vpu_done`
- `TMA_EXEC` — `tma_req` asserted; entered for TMA instruction (MODE=2)
- `TMA_WAIT` — wait for `tma_done`
- `HALT` — execution complete; `done=1`

## Known coverage gaps

- `MXU_EXEC` / `MXU_WAIT` states — no system-level test dispatches an MXU (MODE=1) instruction end-to-end; only unit-level `test_mxu.py` exercises the MXU controller in isolation
- Multi-instruction programs longer than 5 instructions (largest in system tests is 5 instructions in `test_compute_vadd_kernel`)
- PC wrap-around: programs that exceed IRAM[255] not tested
- IRAM word-pair assembly (64-bit instruction from two 32-bit stream words) exercised in all compute tests but never verified by direct IRAM readback

---

## compute_tile.sv (Related Module)

### Role

Top of the compute tile. Glues all compute sub-modules: `tensorcore`, `decoder`, `l1`, `mxu`, `systolic`, `vpu_simd`, `vpu_op`, `vec_regfile`, `pc`. Exposes: start/done handshake to `compute_ctrl`; IRAM write port to `dma_engine`; L1 Port A (DMA port) to `l2_ctrl`; TMA port to `tma_engine`. Applies FP32 clamp ([1e-20, 1e20]) on MXU systolic outputs.

### Test files

- `tpu/verification/compute_tile/test_tensorcore.py` — exercises start/done at the compute_tile level
- `tpu/verification/compute_tile/test_mxu.py` — exercises MXU dispatch path
- `tpu/verification/compute_tile/test_vpu_simd.py` — exercises VPU dispatch path
- `tpu/verification/system/test_tpu_compute.py` — system-level: all four compute tests exercise compute_tile via compute_ctrl

### Test functions exercising this module

| Test function | Test file | Capability exercised |
|---|---|---|
| `test_tensorcore_halt` | `test_tensorcore.py` | start pulse → HALT → done pulse |
| `test_tensorcore_vload_vhalt` | `test_tensorcore.py` | IRAM write, VLOAD dispatch, done |
| `test_tensorcore_vpu_data_flow` | `test_tensorcore.py` | IRAM write, VLOAD→VSTORE identity, L1 Port B |
| `test_compute_identity_kernel` | `test_tpu_compute.py` | System: IRAM write (Port A), start, VLOAD+VSTORE, done, L1 Port A |
| `test_compute_vadd_kernel` | `test_tpu_compute.py` | System: VLOAD×2, VCOMPUTE, VSTORE |
| `test_tma_instruction_in_kernel` | `test_tpu_compute.py` | System: TMA instruction dispatch |
| `test_dma_compute_overlap` | `test_tpu_compute.py` | System: concurrent with dma_engine |

### Behavioral paths covered

- IRAM write via `dma_iram_din` / `instr_write_en` (Port A, DMA engine)
- `start` pulse → `tensorcore` begins fetch cycle
- `done` pulse from `tensorcore` back to `compute_ctrl`
- L1 Port A (DMA): `l2_ctrl` reads and writes L1 BRAM during modes 7/8
- L1 Port B (compute): `tensorcore` / `vpu_simd` / `mxu` drive L1 during kernel execution
- FP32 clamp: active on MXU output path (implicit in any MXU result test)

### Known coverage gaps

- MXU dispatch from system level (no system test runs an MXU matmul kernel end-to-end)
- Simultaneous L1 Port A (l2_ctrl DMA) and Port B (tensorcore) access — port arbitration not tested
- TMA port from kernel to `tma_engine` — only DM→L2 direction tested in system

---

## l1.sv (Related Module)

### Role

L1 data BRAM (8192 × 32-bit words, `blk_mem_gen_0`) with address mux. Dual-port: Port A is the DMA port (driven by `l2_ctrl` for L2↔L1 transfers); Port B is the compute port (driven by `vpu_simd` for VLOAD/VSTORE and by `mxu` for matrix reads/writes). The address mux selects between the DMA pointer and the compute pointer on Port A.

### Test files

- `tpu/verification/compute_tile/test_mxu.py` — Port B (compute): MXU matrix reads
- `tpu/verification/compute_tile/test_vpu_simd.py` — Port B (compute): VLOAD/VSTORE data paths
- `tpu/verification/compute_tile/test_tensorcore.py` — Port B via `test_tensorcore_vpu_data_flow`
- `tpu/verification/system/test_l2_tile.py` — Port A (DMA): `l2_ctrl` writes and reads via modes 7/8
- `tpu/verification/system/test_tpu_compute.py` — Port A (DMA) + Port B (compute) in full flow

### Behavioral paths covered

- Port A write (`l1_dma_wr_en`): `l2_ctrl` writes L2 data to L1 during mode 7
- Port A read (`l1_dma_rd_en`): `l2_ctrl` reads L1 data to L2 during mode 8
- Port B write (`bram_we_b`): `vpu_simd` VSTORE writes vector register to L1
- Port B read (`bram_en_b`, `bram_we_b=0`): `vpu_simd` VLOAD reads L1 into vector register; `mxu` reads weight and activation matrices
- 1-cycle registered read latency modeled correctly in all test drivers

### Known coverage gaps

- Simultaneous Port A and Port B access to the same address — true-dual-port behavior (read-first vs write-first) not tested
- L1 addresses near the 8192-word boundary not tested
