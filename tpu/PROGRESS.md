# Mini-TPU RTL: Progress Log

Tracks completed work and current state. Most recent first.
See `PLAN.md` for goals and `CLAUDE.md` for agent working notes / hardware quirks.

---

## 2026-02-25 — P1.1: Device Memory Emulation Layer (Complete)

**Status: Complete**

Redirected host DMA (modes 1/2) from L1 BRAM to a new device memory module. This separates the host↔device and device→L1 data paths, enabling the future L2 tile (P1.2) to mediate between device memory and L1.

Changes:
- `verification/compute_tile/wrappers/blk_mem_models.sv`: added `blk_mem_gen_2` (65536×32 dual-port behavioral SRAM, 16-bit address)
- `src/system/device_mem.sv` (new): device memory BRAM wrapper with Port A (host DMA) and Port B (L2 stub)
- `src/system/tpu.sv`: instantiate `device_mem`, route DMA write/read to it, tie off compute_tile L1 DMA ports, add `addr_devmem` from `slv_reg4_bus[15:0]` (register 0x10)
- `verification/system/test_tpu.py`: retarget base address register from 0x0C to 0x10
- `verification/system/test_device_mem.py` (new): write/read integrity, multiple sizes (16/64/256), base address offset tests
- `verification/system/Makefile`: add `device_mem.sv` to sources, add `test_device_mem` target

Test result: `make test_data_integrity_rtl` → **TESTS=1 PASS=1 FAIL=0** ✓
Test result: `make test_device_mem` → **TESTS=3 PASS=3 FAIL=0** ✓

**What breaks (expected):** Any test that writes data via mode 1 then computes (mode 3) — data now goes to devmem, not L1. Restored when P1.2 (L2 tile) + P1.3 (L1↔L2 comm instruction) provide the devmem→L2→L1 path.

---

## 2026-02-25 — P0.5 Housekeeping: Rename scratchpad → l1 (Complete)

**Status: Complete**

Renamed the per-tile data memory module to align with architecture naming.

Changes:
- `src/compute_tile/scratchpad.sv` → `src/compute_tile/l1.sv`; module `scratchpad` → `l1`
- `src/compute_tile/compute_tile.sv`: instantiation `scratchpad` → `l1`, `u_scratchpad` → `u_l1`
- `verification/compute_tile/Makefile`: SRC_BRAM path `scratchpad.sv` → `l1.sv`
- `verification/system/Makefile`: source list `scratchpad.sv` → `l1.sv`
- `scripts/package_tpu_ip.tcl`: comment updated
- `CLAUDE.md`: directory structure and module map updated
- `PLAN.md`: all `scratchpad.sv` references updated
- `.gitignore`: removed `CLAUDE.md` exclusion (was stale symlink comment from when AGENTS.md existed)

Test result: `make test_data_integrity_rtl` → **TESTS=1 PASS=1 FAIL=0** ✓

---

## 2026-02-25 — Architecture Pivot: Tensix-Inspired Multi-Tile

**Status: Complete (planning phase)**

Rewrote PLAN.md to reflect new architecture direction:
- **Discarded** original P1 "double-buffer in scratchpad.sv" plan (L2 as second BRAM in scratchpad was wrong)
- **New hierarchy:** L1 (per compute tile) ↔ L2 (separate tile) ↔ Device Memory (DDR/HBM)
- **Data movement** is TPU-initiated via instructions, not host-initiated via tpu_mode
- **Reference architecture:** Tenstorrent Tensix (system-level)
- **MVP target:** 2×2 compute tile mesh + L2 tile + control tile, connected via AXI NoC
- **Device memory:** Currently missing — prototype on Zynq UltraScale+ with partitioned DDR

Housekeeping:
- Removed `tpu/AGENTS.md` (absorbed into CLAUDE.md)
- Replaced `tpu/docs/` symlinks with actual file copies
- Updated CLAUDE.md with new architecture vision

Files changed: `PLAN.md`, `CLAUDE.md`, `PROGRESS.md`
Files removed: `AGENTS.md`
Files replaced (symlink → copy): `docs/isa.md`, `docs/system.md`, `docs/tuda.md`

---

## 2026-02-25 — RTL Sim Data Integrity Fix (Complete)

**Status: Complete**

Root cause (FINAL): `tpu_slave_axi_stream.v` had same IDLE→state reset bug as master.
`reset=1` persists into first WRITE_FIFO cycle; Block 1 resets `write_pointer_stream`
instead of incrementing. Second value (1.0) overwrites address 0.

Fixes applied:
- `tpu_slave_axi_stream.v`: `reset<=0` on IDLE→WRITE_FIFO transition (primary fix, line 123)
- `tpu_master_axi_stream.v`: `valid_data_d3`→`valid_data`, `<N-1`→`<N`, `count<=8` (hang fixes)
- `blk_mem_models.sv`: 3-cycle→1-cycle BRAM latency model (correct for Xilinx BRAM)
- `tpu_master_axi_stream.v`: added `BRAM_READ_LATENCY = 1` localparam for documentation

Test result: `make test_data_integrity_rtl` → **TESTS=1 PASS=1 FAIL=0** ✓

PATTERN TO AVOID: When a state machine uses a `reset` flag asserted in IDLE,
always override it to 0 on the transition OUT of IDLE, or use begin-end blocks.

---

## 2026-02-24 — RTL Sim Data Integrity Fix

**Status: In Progress**

- `test_data_integrity_rtl` was failing: `result[0] = 3.0` instead of `0.0`.
- Root cause: `tpu_master_axi_stream.v` used `count > 2` as the lower bound for
  `init_fill_valid`, skipping 3 pre-loaded BRAM elements. The BRAM has been continuously
  reading `addr=0` during IDLE so `douta=data[0]` is stable before `INIT_COUNTER` starts.
- **Fix applied:**
  - `blk_mem_models.sv`: reduced from 2-cycle to 1-cycle registered output latency to match
    standard Xilinx BRAM IP (no output register).
  - `tpu_master_axi_stream.v`: changed `init_fill_valid` condition from `count > 2 && count < 11`
    to `count < 8 && count < NUMBER_OF_OUTPUT_WORDS` — fires immediately on INIT_COUNTER entry.
- **Pending:** Confirm test passes after changes.

---

## 2026-02-24 — RPC Server with Mock Driver

**Status: Complete**

- Added `runtime/mock_tpu.py` (`MockTpuDriver`) — duck-typed simulation of `TpuDriver` using
  NumPy arrays; no PYNQ required.
- Added `--mock` flag to `runtime/rpc_server.py` to use `MockTpuDriver`.
- Added `runtime/rpc_client.py` (`RemoteTpuDriver`) — TCP drop-in for `TpuDriver`.
- Verified: `make board-test-rpc` against `localhost` completes the full RPC loop.

---

## 2026-02-24 — Systolic Matmul Kernel

**Status: Complete**

- Implemented 32×32 tiled systolic matmul kernel (`.tu` file + program).
- Demonstrated 64×64 matmul via 4 tiles of 32×32.
- Uses `compiler/instructions.py` encoding.

---

## 2026-02-21 — Refactored Systolic GEMM Module

**Status: Complete**

- Created `systolic_tiled_matmul.py`: pure-Python, zero external dependencies.
- Updated `custom_kernels.py` to bridge NumPy calls to this module.
- Verified with `13_transformers.py`.

---

## 2026-02-20 — RTL Simulation: Data Shift Bug Fix

**Status: Complete (superceded by 2026-02-24 fix above)**

- Fixed 1-element data shift in BRAM reads by correcting BRAM model latency.
- Added `FETCH` states to `tensorcore.sv` to handle Instruction 0 read latency.

---

## 2026-02-20 — TPU Compute Hang Resolved

**Status: Complete**

- Fixed `TimeoutError` during `tpu.compute()` caused by RTL race conditions / FSM deadlocks.
- Key fixes: instruction load race (`tpu_slave_axi_stream.v`), port direction error (`tpu.sv`),
  combinational DMA addr (`scratchpad.sv`), BRAM fetch latency states (`tensorcore.sv`),
  watchdog timers (`mxu.sv`, `vpu_simd.sv`).
- `make board-comprehensive` now runs to completion.

---

## Known Open Issues

| Issue | Location | Priority |
|---|---|---|
| Scalar VPU ops are NOPs | `vpu_simd.sv` | P1 |
| DMA off-by-one on large matmuls | `write/read_pointer_stream` | P2 |
| Subnormals (<1.18e-38) cause bus errors | FP32 units | P2 |
| MXU reads at ~33% peak (per-element wait) | `mxu.sv` | P1 |
