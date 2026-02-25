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
         ┌──────────┐                                ┌──────────┐
         │ L2 Tile  │◄──────────────────────────────►│ Control  │
         │ (shared  │                                │  Tile    │
         │  SRAM)   │                                │(host ctl)│
         └────┬─────┘                                └──┬───┬───┘
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

## P0.5 — Housekeeping: Rename scratchpad → L1

### Rename `scratchpad.sv` → `l1.sv`, module `scratchpad` → `l1`
- **Goal:** Align naming with the architecture vision. L1 is the per-tile data memory.
- **RTL:**
  - Rename `src/compute_tile/scratchpad.sv` → `src/compute_tile/l1.sv`
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

### P1.1: Device Memory Emulation Layer
- **Goal:** Add an off-chip device memory concept to the TPU.
- **What:** The current design has no notion of device memory — the host DMA writes directly to L1 BRAM. This is a design mistake. Add a device memory interface so L2↔DevMem can be prototyped.
- **Approach (Zynq UltraScale+):** Partition the PS DDR address space — one region for host, one for device. The TPU accesses "device memory" through AXI-S (reuse existing stream infrastructure as a simple prototype) or AXI-MM.
- **Approach (Alveo U280):** HBM IP provides natural device memory; access via AXI-MM.
- **Prototype first:** Use AXI-S just like the existing host↔TPU interface. AXI-MM for HBM is a later optimization.
- **RTL (new):** `src/system/device_mem_ctrl.sv` — device memory controller/interface
- **RTL (modify):** `src/system/tpu.sv` — address space partitioning, new port wiring
- **Verification (new):** `verification/system/test_device_mem.py` — device memory read/write tests
- **Verification (modify):** `verification/system/Makefile` — add new test target
- **Docs (modify):** `docs/system.md` — add device memory section to register map

### P1.2: L2 Tile (Separate Module)
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

### P1.3: L1 ↔ L2 Communication Instruction
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

### P1.4: L2 ↔ Device Memory TMA Instruction
- **Goal:** Design a TMA (Tensor Memory Access) instruction for L2↔DevMem transfers.
- **What:** Handles address generation and burst transfers between L2 SRAM and device memory.
- **Prototype:** Simple contiguous block transfer (no coalescing). Coalescing and strided access are future (P3.5).
- **RTL (modify):** `src/l2_tile/l2_tile.sv` — TMA engine, DevMem request/response logic
- **RTL (new):** `src/l2_tile/tma_engine.sv` — address generation + burst controller
- **Verification (new):** `verification/l2_tile/test_tma.py` — TMA transfer correctness
- **Verification (modify):** `verification/l2_tile/Makefile`
- **Docs (modify):** `docs/isa.md` — TMA instruction encoding
- **Compiler (modify):** `compiler/assembler.py` — TMA mnemonic
- **Dependency:** P1.1 (device memory) + P1.2 (L2 tile).

### P1.5: MXU Pipelined Burst Mode
- **Goal:** Refactor `mxu.sv` from per-element `MEM_LATENCY` wait to true pipelined burst reads.
- **Impact:** ~3x throughput improvement on large matmuls (current ~33% peak utilization).
- **RTL (modify):** `src/compute_tile/mxu.sv` — pipelined burst FSM
- **RTL (modify):** `src/compute_tile/l1.sv` — may need burst-ready Port B interface
- **Verification (modify):** `verification/compute_tile/test_mxu.py` — burst mode tests
- **Dependency:** Stable L1 interface (P1.3 should not break existing Port B interface).

### P1.6: Scalar VPU Ops (Currently NOPs)
- **Goal:** Implement real scalar operations in `vpu_simd.sv` instead of watchdog-guarded NOPs.
- **RTL (modify):** `src/compute_tile/vpu_simd.sv` — scalar dispatch path fix
- **RTL (modify):** `src/compute_tile/vpu_op.sv` — scalar operation implementation
- **Verification (modify):** `verification/compute_tile/test_vpu_simd.py` — scalar op tests

### P1.7: ISA Documentation Overhaul
- **Goal:** Consolidate and clean up ISA documentation. Single source of truth is `tpu/docs/isa.md`.
- **Docs (modify):** `docs/isa.md` — clean up, add L1↔L2 comm and TMA instruction specs
- **Docs (modify):** `docs/system.md` — update register map with device memory, L2
- **Docs (modify):** `docs/tuda.md` — update programming model for new memory hierarchy
- **Note:** ISA changes must be coordinated between RTL (`decoder.sv`) and compiler (`assembler.py`).

---

## P2 — Medium-Term: Multi-Tile Mesh

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

### P3.1: RTL Correctness: DMA Off-by-One
- **Goal:** Fix minor DMA address off-by-one causing numerical mismatches in large matmul results.
- **RTL (modify):** `src/system/tpu_slave_axi_stream.v` and/or `src/system/tpu_master_axi_stream.v`
- **Verification (modify):** `verification/system/test_tpu.py` — add large-transfer edge case tests

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
