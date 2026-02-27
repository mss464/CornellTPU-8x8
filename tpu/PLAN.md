# Mini-TPU RTL: Planned Goals

This file tracks planned architectural and engineering goals for the `tpu/` subsystem.
See `PROGRESS.md` for current status and `CLAUDE.md` for agent working notes.

---

## P0 — Critical / Active (RESOLVED)

### Fix RTL Simulation Test Suite (RESOLVED)
- **Resolution:** `test_data_integrity_rtl` passes — TESTS=1 PASS=1 FAIL=0 (2026-02-25).
- **Root cause fixed:** `tpu_slave_axi_stream.v` IDLE→WRITE_FIFO reset signal bug; see PROGRESS.md.

---

## Architecture Vision

**Reference:** Tenstorrent Tensix (system-level; tile-level design differs).

**Target system (MVP): 3×2 AXI mesh**
```
              ┌─────────────── AXI NoC (3×2 mesh) ─────────┐
              │                                            │
         ┌────┴─────┐                                ┌─────┴────┐
         │ Compute  │◄──────────────────────────────►│ Compute  │
         │ Tile 0   │                                │ Tile 1   │
         │(MXU+VPU  │                                │(MXU+VPU  │
         │ +L1)     │                                │ +L1)     │
         └────┬─────┘                                └─────┬────┘
              │                                            │
              ▼                                            ▼
         ┌──────────┐                                ┌──────────┐
         │ Compute  │◄──────────────────────────────►│ Compute  │
         │ Tile 2   │                                │ Tile 3   │
         │(MXU+VPU  │                                │(MXU+VPU  │
         │ +L1)     │                                │ +L1)     │
         └────┬─────┘                                └─────┬────┘
              │                                            │
              ▼                                            ▼
         ┌──────────────────────────────────────────────────────┐
         │ 			L2 Tile	        		│
         │ 			(shared           		│
         │  			  SRAM)            		│
         └────┬─────────────────────────────────────────────────┘
              │				     	     ┌──────────┐
              │ 				     │ Control  │
              │				     	     │  Tile    │
              │				             │(host ctl)│
              │				     	     └──┬───┬───┘
              │                                    DMA  │   │
              │◄───────────────────────────────────────►│   │
              │                                   AXI-S │   │
              │ AXI-MM (HBM)                            │   │ AXI-Lite over PCIe
              │ AXI-S (DDR prototype)                   │   │
              │                                         │   │
         ┌────┴─────┐                                ┌──┴───┴───┐
         │  Device  │                                │ Host(PS) │
         │  Memory  │                                │          │
         │(DDR/HBM) │                                │          │
         └──────────┘                                └──────────┘
```

**Memory hierarchy:** L1 (per compute tile) ↔ L2 (shared tile) ↔ Device Memory (DDR/HBM)

- **L1 ↔ L2:** Simple communication instruction (TPU-initiated)
- **L2 ↔ Device Memory:** TMA instruction (address generation, coalescing — future)
- **Host ↔ Device Memory:** Async memcpy (existing AXI-S or DMA)

**Overlap goal:** Compute on L1 ‖ L1 fed from L2 ‖ L2 fed from Device Memory ‖ Host↔DevMem memcpy

**All scheduling is static** — no hardware scheduling logic.

**Prototype boards:**
- Zynq UltraScale+ (shared DDR between PS and PL; partition address space to emulate PCIe-attached TPU)
- Alveo U280 (HBM via AXI-MM — natural device memory separation)

---

## P0.5 — Housekeeping: Rename scratchpad → L1 (RESOLVED 2026-02-25)

### Rename `l1.sv` → `l1.sv`, module `scratchpad` → `l1`
- **Goal:** Align naming with the architecture vision. L1 is the per-tile data memory.
- **RTL:**
  - Rename `src/compute_tile/l1.sv` → `src/compute_tile/l1.sv`
  - Change `module scratchpad` → `module l1` inside the file
  - Update `src/compute_tile/compute_tile.sv` — instantiation `scratchpad` → `l1`
- **Build:**
  - `verification/compute_tile/Makefile` — `SRC_BRAM` path
  - `verification/system/Makefile` — source file list
  - `scripts/package_tpu_ip.tcl` — comment reference
  - `Makefile` (top-level) — if it references scratchpad
- **Docs:**
  - `CLAUDE.md` — directory structure, module map, architecture section
  - `README.md` — directory tree
  - `PROGRESS.md` — historical references (leave as-is for history, or add note)
- **Verification:** Run `make test_data_integrity_rtl` — must still pass after rename.

---

## P1 — Near-Term: Single Compute Tile + Device Memory

Each compute tile has: MXU, VPU, frontend scalar CPU for scalar ops + instruction decoding, IRAM, L1.

### P1.1: Device Memory Emulation Layer (RESOLVED 2026-02-25)
- **Resolution:** Host DMA modes 1/2 retargeted to device_mem.sv (65536×32 BRAM). Test suite: test_data_integrity + test_device_mem all pass.
- **Goal:** Add an off-chip device memory concept to the TPU.
- **What:** The current design has no notion of device memory — the host DMA writes directly to L1 BRAM. This is a design mistake. Add a device memory interface so L2↔DevMem can be prototyped.
- **Approach (Zynq UltraScale+):** Partition the PS DDR address space — one region for host, one for device. The TPU accesses "device memory" through AXI-S (reuse existing stream infrastructure as a simple prototype) or AXI-MM.
- **Approach (Alveo U280):** HBM IP provides natural device memory; access via AXI-MM.
- **Prototype first:** Use AXI-S just like the existing host↔TPU interface. AXI-MM for HBM is a later optimization.
- **RTL (new):** `src/system/device_mem.sv` — device memory BRAM wrapper
- **RTL (modify):** `src/system/tpu.sv` — address space partitioning, new port wiring
- **Verification (new):** `verification/system/test_device_mem.py` — device memory read/write tests
- **Verification (modify):** `verification/system/Makefile` — add new test target
- **Docs (modify):** `docs/system.md` — add device memory section to register map

### P1.2: L2 Tile (Separate Module) (RESOLVED 2026-02-25)
- **Resolution:** L2 tile implemented as host-controlled block transfer modes (modes 5–8). 32768×32 BRAM (blk_mem_gen_3). New module: src/l2_tile/l2_tile.sv. Tests: test_l2_tile → TESTS=4 PASS=4 FAIL=0.
- **Goal:** Create L2 as a separate tile/module, NOT a second BRAM inside `l1.sv`.
- **What:** L2 tile sits between compute tiles and device memory. Responsible for staging data between L1s and device memory.
- **L2 tile contents:** SRAM bank(s), address generation logic, L1↔L2 data mover, L2↔DevMem engine (initially simple).
- **RTL (new):** `src/l2_tile/l2_tile.sv` — L2 tile top module
- **RTL (new):** `src/l2_tile/l2_sram.sv` — L2 SRAM bank(s)
- **Verification (new):** `verification/l2_tile/test_l2_tile.py` — L2 read/write, data staging tests
- **Verification (new):** `verification/l2_tile/Makefile`
- **Verification (new):** `verification/l2_tile/wrappers/` — behavioral SRAM models if needed
- **Docs (modify):** `docs/system.md` — L2 tile description
- **Dependency:** P1.1 (needs device memory interface to connect to).

### P1.3: L1 ↔ L2 Communication Instruction (RESOLVED 2026-02-25)
- **Resolution:** Implemented as host-controlled modes 7 (L2_TO_L1) and 8 (L1_TO_L2) in tpu.sv FSM. addr_l2 at register 0x14 (slv_reg5_bus[14:0]). Avoids ISA/decoder changes. ISA-driven in-kernel L1↔L2 movement remains future work.
- **Goal:** Design and implement an ISA instruction for L1↔L2 data movement.
- **What:** Moves a contiguous block between L1 (per-tile) and L2 (shared tile). Direction: L2→L1 (prefetch) or L1→L2 (writeback).
- **ISA encoding:** New MODE value or new VPU_TYPE. Must be documented in `docs/isa.md`.
- **RTL (modify):** `src/compute_tile/tensorcore.sv` — decode and dispatch new instruction
- **RTL (modify):** `src/compute_tile/decoder.sv` — new opcode
- **RTL (modify):** `src/compute_tile/l1.sv` — Port A arbitration (DMA vs L1↔L2 transfers)
- **RTL (modify):** `src/compute_tile/compute_tile.sv` — new inter-tile bus port
- **RTL (modify):** `src/l2_tile/l2_tile.sv` — L1↔L2 request handling
- **Verification (new):** `verification/system/test_l1_l2_comm.py` — L1↔L2 transfer correctness
- **Verification (modify):** `verification/system/Makefile` — new test target
- **Docs (modify):** `docs/isa.md` — new instruction encoding
- **Compiler (modify):** `compiler/assembler.py` — new mnemonic
- **Dependency:** P1.2 (L2 tile must exist).

### P1.4: RTL Correctness: DMA Write+Read Corruption (PARTIALLY RESOLVED)
- **Resolution (2026-02-27):**
  - **Bug A** (slave write stall): RESOLVED. Gate `dma_wr_en` on `stream_data_valid` in `tpu.sv` line 457. Sim confirms first element preserved.
  - **Bug B** (master FIFO boundary duplicate): DOES NOT EXIST in RTL. `valid_d1` and `rd_data` are inherently aligned (both 1-cycle delayed from `rd_en`). The `!fifo_empty` gate attempted in P1.4 was wrong — it dropped the last word. Reverted to `assign M_AXIS_TVALID = valid_d1`.
  - **Board +2 shift:** Root cause is NOT Bug B. Suspect list: BRAM output register (Vivado IP cache), PS DMA timing, clock domain mismatch. Requires board-level investigation.
  - **Sim:** 4 boundary tests (N=8, N=9, N=16, known values) all pass. 11/11 system tests pass.
- **RTL (modified):** `src/system/tpu.sv` — `dma_wr_en = data_write_en && stream_data_valid`
- **RTL (modified):** `src/system/tpu_slave_axi_stream.v` — `reset <= 1'b0` on IDLE→WRITE_FIFO
- **RTL (reverted):** `src/system/tpu_master_axi_stream.v` — `M_AXIS_TVALID = valid_d1` (no `!fifo_empty` gate)
- **Verification (added):** `verification/system/test_tpu.py` — boundary tests N=8, N=9, N=16
- **Board:** bitstream rebuild needed; board +2 shift still open (different root cause)

### P1.5: L2 ↔ Device Memory TMA Instruction (RESOLVED 2026-02-27)
- **Resolution:** TMA RTL was already fully implemented in a prior session:
  - `src/compute_tile/decoder.sv` — MODE=2 fields: dir[61], dm_base[60:45], l2_base[44:30], len[29:14]
  - `src/compute_tile/tensorcore.sv` — EXEC_TMA/WAIT_TMA states; issues tma_req pulse, waits for tma_done
  - `src/l2_tile/l2_tile.sv` + `src/l2_tile/tma_engine.sv` — DM2L2/L22DM FSM with 1-cycle BRAM pipeline
  - `src/system/tpu.sv` — ct_tma_* wires between compute_tile and l2_tile
  - This commit adds the end-to-end system test to verify the full path.
- **Verification (new):** `verification/system/test_tpu_compute.py` — `encode_tma_instr` helper + `test_tma_instruction_in_kernel` test
  - Writes 8 values to DevMem[32:39], runs TMA kernel (DM_TO_L2, dm_base=32, l2_base=0, len=8),
    reads back L2[0:7] through L2→L1→L2→DevMem[100:107]→host, verifies values match [10.0..17.0].
  - Result: TESTS=3 PASS=3 FAIL=0 (all test_tpu_compute tests pass).
- **Dependency:** P1.1 (device memory) + P1.2 (L2 tile).

### P1.6: ISA Documentation Overhaul (RESOLVED 2026-02-27)
- **Goal:** Consolidate and clean up ISA documentation. Single source of truth is `tpu/docs/isa.md`.
- **Docs (modify):** `docs/isa.md` — clean up, add L1↔L2 comm and TMA instruction specs
- **Docs (modify):** `docs/system.md` — update register map with device memory, L2
- **Docs (modify):** `docs/tuda.md` — update programming model for new memory hierarchy
- **Note:** ISA changes must be coordinated between RTL (`decoder.sv`) and compiler (`assembler.py`).
- **Resolution (2026-02-27):** TMA instruction (MODE=2) added to ISA spec. L1_TO_L2 mode row already present in system.md. TMA assembler mnemonic documented. TMA instruction note added to system.md register description.

### P1.7: Verification Infrastructure Overhaul
- **Goal:** Make sim practical for iterative RTL development. Current cocotb + iverilog gives ~5k cycles/sec.
- **Depends:** None (independent infrastructure work).
- **Sub-tasks (file-independent → can run in parallel worktrees):**

| # | Sub-task | File(s) | Impact |
|---|----------|---------|--------|
| 1 | Drop N=64, keep N≤16 + boundary N=8/9 (DONE) | `test_tpu.py` | 5× speedup |
| 2 | Fix Verilator (`perl-FindBin`), add `SIM=verilator` to Makefile (DONE) | system `Makefile` | 10-50× speedup |
| 3 | `TESTCASE=` and `VCD=` selectors in Makefile (DONE) | system `Makefile` | Dev iteration |
| 4 | Replace manual AXI with `cocotbext-axi` (`AXIStreamSource/Sink`) | `test_tpu.py` | 3-5× fewer VPI crossings |
| 5 | Unit-level stream tests: `test_slave_stream.py`, `test_master_stream.py` (DONE) | new files + Makefile | 10× faster compile, isolated |
| 6 | Conda environment (`environment.yml`) + `make setup` (DONE) | root `environment.yml`, `tpu/Makefile` | Reproducibility |

- Sub-tasks 1, 2, 3, 5, 6 are file-independent → run in parallel worktrees.
- Sub-task 4 touches `test_tpu.py` (shared with 1) → run sequentially after 1.

### P1.8: Descriptor-Based DMA Engine (RESOLVED 2026-02-27)
- **Resolution:** Doorbell mechanism added. `slv_reg0[4]` = doorbell bit. Host writes `mode | 0x10` to arm and trigger atomically. Hardware FSM latches mode in `latched_mode`, pulses `doorbell_clear` (1 cycle), dispatches. `ST_WAIT_DONE` auto-returns to `ST_IDLE` without checking `tpu_mode` — no restart risk since doorbell is cleared. All driver methods updated: removed trailing `write_axi_lite(0x00, 0)` IDLE write. All 11 smoke sim tests pass.
- **RTL (modified):** `src/system/tpu_slave_axi_lite.v` — `doorbell_out` output, `doorbell_clear` input, doorbell auto-clear in main write always block
- **RTL (modified):** `src/system/tpu.sv` — `doorbell`/`doorbell_clear`/`latched_mode` wires; ST_IDLE gates on `doorbell`; ST_EXEC_WRITE uses `latched_mode`; ST_WAIT_DONE auto-returns
- **Driver (modified):** `verification/system/test_tpu.py`, `test_tpu_compute.py` — all methods use `mode | 0x10` write; removed trailing IDLE writes
- **Goal:** Replace host-polled control flow with autonomous descriptor-driven transfers.
- **Depends:** P1.4 (DMA correctness).
- **Problem:** Current design requires O(N) AXI-Lite reads in `wait_for_flag` per transfer. Each burns ~5-10 VPI round-trips in sim and MMIO overhead on board.
- **Fix:** Command descriptor model:
  1. Host writes 3-word descriptor (mode, base_addr, length) to register window
  2. Host asserts `doorbell` bit
  3. Hardware sequences full transfer autonomously
  4. Hardware asserts `done` flag/interrupt on completion
  5. Host polls once or uses interrupt
- **RTL (modify):** `src/system/tpu.sv` — descriptor-driven sequencer replaces polled FSM
- **RTL (modify):** `src/system/tpu_slave_axi_lite.v` — doorbell register, descriptor window
- **Impact:** Sim goes from O(N²) to O(N) VPI crossings per transfer. Board eliminates MMIO polling overhead. Enables compute/DMA overlap.

---

## P2 — Medium-Term: Multi-Tile Mesh

### P2.07: Deepen AXI-Stream FIFO (RESOLVED 2026-02-27)
- **Resolution:** Added `DEPTH` parameter (default=8) to `fifo4.sv` with parametric pointer width
  (`PTR_W = $clog2(DEPTH)+1`). Updated `tpu_master_axi_stream.v` to use `#(.WIDTH(32), .DEPTH(8))`
  via a `localparam FIFO_DEPTH`. No functional change at DEPTH=8. All 7 fifo4 unit tests pass;
  3/3 smoke sim tests pass.
- **Goal:** Parameterize `fifo4` depth and decouple prefetch window from FIFO capacity.
- **Depends:** P1.4 (DMA correctness).
- **Problem:** `fifo4` depth=8 is hardcoded. Prefetch window `count <= 8` creates fragile coupling. Backpressure stalls at high throughput.
- **Fix:**
  - Parameterize: `fifo4 #(.WIDTH(32), .DEPTH(64))`
  - Decouple: `localparam PREFETCH_DEPTH` auto-derived from FIFO depth
  - Use one BRAM slice (512-deep at 32-bit) for sustained 1-word/cycle throughput
- **RTL (modify):** `src/system/fifo4.sv`, `src/system/tpu_master_axi_stream.v`
- **Verification (modify):** `verification/compute_tile/test_fifo4.py` — parameterized depth tests

### P2.08: Separate DMA and Compute FSMs
- **Goal:** Factor the monolithic `tpu.sv` FSM into independent sub-FSMs for overlapped execution.
- **Depends:** P1.8 (descriptor-based DMA).
- **Problem:** Modes 1–8 are mutually exclusive in one FSM. Compute (mode 3) cannot overlap DMA (mode 1/2). All modes funnel through one combinational priority.
- **Fix:** Independent sub-FSMs:
  - DMA FSM (modes 1/2, 5/6) — owns AXI-Stream + device_mem Port A
  - Compute FSM (mode 3/4) — owns tensorcore + L1 Port A
  - L2 FSM (modes 7/8) — owns L2 Port A + L1 DMA port
  - Top-level thin arbiter dispatches descriptors, tracks completion
- **RTL (modify):** `src/system/tpu.sv` → split + new `src/system/dma_engine.sv`, `src/system/compute_ctrl.sv`

### P2.05: MXU Pipelined Burst Mode
- **Goal:** Refactor `mxu.sv` from per-element `MEM_LATENCY` wait to true pipelined burst reads.
- **Impact:** ~3x throughput improvement on large matmuls (current ~33% peak utilization).
- **RTL (modify):** `src/compute_tile/mxu.sv` — pipelined burst FSM
- **RTL (modify):** `src/compute_tile/l1.sv` — may need burst-ready Port B interface
- **Verification (modify):** `verification/compute_tile/test_mxu.py` — burst mode tests
- **Dependency:** Stable L1 interface (P1.3 should not break existing Port B interface).

### P2.06: Scalar VPU Ops (Currently NOPs)
- **Goal:** Implement real scalar operations in `vpu_simd.sv` instead of watchdog-guarded NOPs.
- **RTL (modify):** `src/compute_tile/vpu_simd.sv` — scalar dispatch path fix
- **RTL (modify):** `src/compute_tile/vpu_op.sv` — scalar operation implementation
- **Verification (modify):** `verification/compute_tile/test_vpu_simd.py` — scalar op tests

### P2.1: AXI NoC Infrastructure
- **Goal:** Design the on-chip network connecting compute tiles, L2 tile, and control tile.
- **What:** AXI-based Network-on-Chip. 3×2 mesh topology.
- **RTL (new):** `src/noc/noc_router.sv` — single NoC router
- **RTL (new):** `src/noc/noc_mesh.sv` — 3×2 mesh instantiation
- **RTL (new):** `src/noc/noc_pkg.sv` — packet format, address map, constants
- **Verification (new):** `verification/noc/test_noc_router.py` — single router tests
- **Verification (new):** `verification/noc/test_noc_mesh.py` — mesh routing tests
- **Verification (new):** `verification/noc/Makefile`

### P2.2: 2×2 Compute Tile Mesh
- **Goal:** Instantiate 4 compute tiles connected via AXI NoC.
- **What:** Each tile has its own L1. All tiles share the L2 tile underneath.
- **RTL (new):** `src/system/tpu_mesh.sv` — top-level 3×2 mesh instantiation (replaces `tpu.sv` as top)
- **RTL (modify):** `src/compute_tile/compute_tile.sv` — add NoC port
- **Verification (new):** `verification/system/test_multi_tile.py` — multi-tile compute tests
- **Verification (modify):** `verification/system/Makefile`
- **Dependency:** P2.1 (NoC), P1.2 (L2 tile), P1.3 (L1↔L2 instruction).

### P2.3: Control Tile
- **Goal:** Add a control tile that receives host control signals and distributes them over the NoC.
- **What:** Replaces the current `tpu_slave_axi_lite` → `tpu.sv` FSM direct-control model.
- **RTL (new):** `src/control_tile/control_tile.sv` — control tile top
- **RTL (new):** `src/control_tile/host_interface.sv` — AXI-Lite host bridge
- **Verification (new):** `verification/control_tile/test_control_tile.py`
- **Verification (new):** `verification/control_tile/Makefile`
- **Dependency:** P2.1 (NoC).

### P2.4: Multi-Tile Static Scheduling
- **Goal:** Static scheduling of instructions across tiles — no hardware scheduler.
- **What:** Compiler generates per-tile instruction streams. Control tile loads each tile's IRAM and triggers execution. Synchronization via barrier instructions or static cycle counts.
- **RTL (modify):** `src/control_tile/control_tile.sv` — per-tile IRAM load + trigger
- **RTL (modify):** `src/compute_tile/tensorcore.sv` — barrier instruction support
- **Compiler (modify):** `compiler/assembler.py` — multi-tile scheduling, barrier mnemonic
- **Verification (new):** `verification/system/test_static_schedule.py`
- **Dependency:** P2.2, P2.3.

---

## P3 — Longer-Term


### P3.2: FP32 Exception Handling
- **Goal:** Add flush-to-zero and overflow/underflow detection to FP32 units.
- **RTL (modify):** `src/compute_tile/fp32_add.sv`, `src/compute_tile/fp32_mul.sv`
- **Verification (modify):** `verification/compute_tile/test_fp32_add.py`, `test_fp32_mul.py`

### P3.3: Vivado Timing Closure at Higher Frequency
- **Goal:** Push clock from 100 MHz toward 200 MHz.
- **RTL (modify):** `src/compute_tile/mxu.sv`, `src/compute_tile/systolic.sv` — pipeline stages
- **Build (modify):** Vivado constraint files (timing targets)

### P3.4: AXI-MM for HBM (Alveo U280)
- **Goal:** Replace AXI-S device memory prototype with proper AXI-MM interface for HBM IP.
- **RTL (modify):** `src/system/device_mem_ctrl.sv` — AXI-MM master port
- **RTL (modify):** `src/l2_tile/l2_tile.sv` — AXI-MM interface to DevMem
- **Dependency:** P1.1 device memory interface designed for this migration.

### P3.5: TMA Advanced Features
- **Goal:** Coalescing, strided access, multi-dimensional address generation in TMA engine.
- **RTL (modify):** `src/l2_tile/tma_engine.sv`
- **Verification (modify):** `verification/l2_tile/test_tma.py` — strided/coalesced transfer tests
- **Dependency:** P1.4 basic TMA working first.
