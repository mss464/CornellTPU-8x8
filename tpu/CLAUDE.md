# CLAUDE.md — TPU RTL Project Guide

> This project implements a full TPU accelerator in RTL with automated verification.
> **Read first:** [`PLAN.md`](PLAN.md) — planned goals (grouped by priority P0–P3) · [`PROGRESS.md`](PROGRESS.md) — change log

---

## Project Goal

`tpu/` is a self-contained RTL implementation project for a custom TPU, targeting Zynq UltraScale+ and Alveo U280 FPGAs. The full stack spans RTL → Vivado IP packaging → bitstream → host driver. The architecture is inspired by Tenstorrent Tensix at the system level: compute tiles (MXU + VPU + scalar frontend + IRAM + L1) connected via AXI NoC to a shared control tile, shared L2 tile to device memory. Agents should drive the full cycle: write RTL, run simulation verification, fix failures, and update documentation.

---

## How Agents Should Work

1. **Read `PLAN.md` first** — find the highest-priority unresolved task (lowest Pn number, not marked RESOLVED). Each task lists its source files, verification files, and dependencies.
2. **Read `PROGRESS.md`** — understand what was last attempted and its outcome.
3. **Write RTL, run tests, fix failures** — iterate until `make test_data_integrity_rtl` passes.
4. **Commit each unit of work atomically** — one logical change per commit. This ensures reversibility (`git revert`) if a change breaks tests. Never bundle unrelated changes.
5. **Update `PROGRESS.md`** — add a dated entry with root cause, fix, and files changed.
6. **Update `PLAN.md`** — mark completed tasks as (RESOLVED).

**Context rule:** This file (`CLAUDE.md`) + `PLAN.md` + `PROGRESS.md` must be sufficient for a fresh agent to start working. Do not store project context anywhere else.

## Execution Rules

These rules govern how work is structured and handed off between agents.

### Model selection
- **Ask the user to switch model only at phase boundaries** (e.g., finishing mechanical work before starting open-ended design, or vice versa). Do not ask mid-task or for small decisions — conserve output tokens.
- Suggested defaults by task type:

| Task type | Model |
|-----------|-------|
| Architectural design, open-ended RTL | opus |
| Targeted RTL edits with full spec | sonnet |
| Mechanical rename / string replace / doc edits | haiku |
| Verification run (skill/command) | skill (`/tpu-test`) |

### Parallelism
- **Mechanical tasks (rename, string replace, doc edits) MUST use haiku agents**, not the current model directly — even if it would work.
- Independent file edits → launch as parallel **background worktree haiku agents** (one agent per file or logical group).
- Tasks with shared file dependencies → run sequentially in foreground.
- Never let two agents edit the same file simultaneously.
- Example for a rename across 6 files: group into 3 independent pairs, launch 3 parallel haiku agents with `isolation: "worktree"`.

### Reversibility
- Each agent must produce **one atomic git commit** per logical unit of work before returning.
- Commit message format: `"<verb>) <what> — <why>"` (e.g., `"rename) scratchpad → l1 — align with architecture naming"`)
- This guarantees `git revert <sha>` can undo any single step without touching adjacent work.

### Worktrees
- Use `isolation: "worktree"` for parallel haiku agents doing independent edits.
- Use foreground (main worktree) for sequential steps that build on each other.

### Skills / commands
- Use `/tpu-smoke` for quick PASS/FAIL-only smoke test (saves context window).
- Use `/tpu-test` to run the verification suite — do not inline `make` calls for this.
- Use `/tpu-progress` to append to PROGRESS.md after completing a task.
- Use `/tpu-status` to get a current summary before starting a new task.

---

## Context Loading Guide

Every doc, source, and test file is a self-contained module. Load only what you need.
Do NOT truncate file content to save context — swap entire files in/out instead.

| Working on... | Docs to load | Sources | Tests |
|---------------|-------------|---------|-------|
| DMA write/read | data_movement.md, xilinx_block_design.md | system/tpu_master_axi_stream.v, system/tpu_slave_axi_stream.v | system/test_tpu.py, system/test_device_mem.py |
| Compute (MXU) | isa.md, bram_specs.md | compute_tile/mxu.sv, compute_tile/systolic.sv | compute_tile/test_mxu.py |
| Compute (VPU) | isa.md, bram_specs.md | compute_tile/vpu_simd.sv, compute_tile/vpu_op.sv | compute_tile/test_vpu_simd.py |
| L2 hierarchy | data_movement.md, bram_specs.md | l2_tile/*.sv, system/l2_ctrl.sv | system/test_l2_tile.py, l2_tile/test_tma.py |
| Board debugging | board_bugs.md, xilinx_block_design.md | (failing module) | board_tests/test_board.py |
| ISA changes | isa.md | compute_tile/decoder.sv, compute_tile/tensorcore.sv | compute_tile/test_decoder.py |
| System registers | system.md | system/tpu_slave_axi_lite.v | (manual/board) |
| BRAM timing | bram_specs.md | (relevant mem module) | (relevant test) |
| Verification | verify_\<module\>.md | (module under test) | (test file) |

---

## Directory Structure

```
tpu/
├── CLAUDE.md              ← this file (agent-facing guide)
├── PLAN.md                ← planned goals by priority
├── PROGRESS.md            ← change log and open issues
├── Makefile               ← top-level build targets (Vivado, packaging, deploy)
├── hw_config.json         ← FPGA IP names for the host driver
│
├── docs/                  ← reference documentation (modular, self-contained files)
│   ├── isa.md             ← Instruction set specification
│   ├── system.md          ← AXI register map, programming model, doorbell protocol
│   ├── tuda.md            ← Host-device programming model (TUDA API)
│   ├── memory_hierarchy.md  ← Overview + ASCII diagram (links to component docs)
│   ├── bram_specs.md      ← BRAM component specs, latency invariant, sim/HW alignment
│   ├── data_movement.md   ← Modes 1–8 datapath, cycle traces, TMA instruction flow
│   ├── board_bugs.md      ← DMA corruption root causes (Bug A + B), fix strategy
│   ├── xilinx_block_design.md ← Vivado IPI block design, AXI DMA protocol, address map
│   ├── verify_overview.md ← Module coverage matrix, test infrastructure
│   ├── verify_<module>.md ← Per-module verification spec (~18 files)
│   ├── verify_board.md    ← Board test harness, known hardware issues
│   └── verify_coverage.md ← Verilator coverage collection procedure
│
├── src/                   ← RTL source (synthesizable)
│   ├── system/            ← Top-level AXI integration
│   │   ├── tpu.sv                    TOP module; FSM, BRAM routing, AXI glue
│   │   ├── tpu_slave_axi_lite.v      AXI-Lite register slave (host → ctrl regs)
│   │   ├── tpu_slave_axi_stream.v    AXI-Stream sink (DMA write path)
│   │   ├── tpu_master_axi_stream.v   AXI-Stream source (DMA read path)
│   │   ├── fifo4.sv                  FWFT synchronous FIFO (depth=64, used by master stream)
│   │   └── device_mem.sv             Device memory BRAM (host DMA target)
│   │
│   ├── l2_tile/           ← L2 shared SRAM tile
│   │   └── l2_tile.sv                L2 tile top; 32768×32 SRAM, DevMem↔L2 FSM
│   │
│   └── compute_tile/      ← The accelerator core
│       ├── compute_tile.sv           Top of compute tile; glues all units
│       ├── tensorcore.sv             Instruction fetch / dispatch FSM
│       ├── decoder.sv                64-bit ISA instruction decoder
│       ├── pc.sv                     Program counter
│       ├── l1.sv                     L1 data BRAM (blk_mem_gen_0) + address mux
│       ├── mxu.sv                    Matrix unit controller (reads BRAM, drives systolic)
│       ├── systolic.sv               Systolic array tile
│       ├── pe.sv                     Single processing element (MAC)
│       ├── vpu_simd.sv               SIMD VPU controller
│       ├── vpu_op.sv                 Per-lane vector operation (add/mul/relu/etc.)
│       ├── vec_regfile.sv            Vector register file (8 registers × 8 lanes)
│       ├── fp32_add.sv               IEEE-754 FP32 adder
│       └── fp32_mul.sv               IEEE-754 FP32 multiplier
│
├── verification/          ← Simulation testbenches (cocotb + Icarus Verilog)
│   ├── README.md
│   ├── compute_tile/      ← Unit tests for each submodule
│   │   ├── Makefile                  Targets: test_<module> for each unit
│   │   ├── wrappers/
│   │   │   ├── bram_l1_data.sv       L1 data BRAM model (blk_mem_gen_0, 8192×32)
│   │   │   ├── bram_iram.sv          Instruction RAM model (blk_mem_gen_1, 256×64)
│   │   │   ├── bram_device_mem.sv    Device memory model (blk_mem_gen_2, 65536×32)
│   │   │   ├── bram_l2_sram.sv       L2 shared SRAM model (blk_mem_gen_3, 32768×32)
│   │   │   └── blk_mem_models.sv     Legacy: all 4 models in one file (still valid)
│   │   ├── test_decoder.py
│   │   ├── test_fifo4.py
│   │   ├── test_fp32_add.py
│   │   ├── test_fp32_mul.py
│   │   ├── test_mxu.py
│   │   ├── test_pe.py
│   │   ├── test_systolic_array.py
│   │   ├── test_tensorcore.py
│   │   ├── test_vpu_op.py
│   │   ├── test_vpu_simd.py
│   │   └── test_vec_regfile.py
│   └── system/            ← System-level integration tests
│       ├── Makefile                  Targets: test_data_integrity_rtl, test_device_mem, test_l2_tile
│       ├── test_tpu.py               TpuRtlDriver + AXI-Stream write→compute→read integrity test
│       ├── test_device_mem.py        Device memory read/write integrity tests
│       ├── test_l2_tile.py           L2 tile and L1↔L2 hierarchy transfer tests
│       └── diagnose_ip.py            Debug helper
│
└── scripts/               ← Vivado automation
    ├── build_bd_bitstream.tcl        Block design + bitstream generation
    ├── package_compute_tile_ip.tcl   Package compute_tile as Vivado IP
    ├── package_tpu_ip.tcl            Package full TPU as Vivado IP
    └── program_fpga.py               Board programming helper
```

---

## Module Map

| Module | File | Role |
|---|---|---|
| `tpu` | `src/system/tpu.sv` | Top; FSM, AXI routing |
| `tpu_slave_axi_lite` | `system/tpu_slave_axi_lite.v` | Host register access |
| `tpu_slave_axi_stream` | `system/tpu_slave_axi_stream.v` | DMA write to BRAM |
| `tpu_master_axi_stream` | `system/tpu_master_axi_stream.v` | DMA read from BRAM |
| `device_mem` | `system/device_mem.sv` | Device memory (host DMA target) |
| `l2_tile` | `l2_tile/l2_tile.sv` | L2 shared SRAM; DevMem↔L2 FSM |
| `compute_tile` | `compute_tile/compute_tile.sv` | Accelerator top |
| `tensorcore` | `compute_tile/tensorcore.sv` | Fetch + dispatch |
| `l1` | `compute_tile/l1.sv` | L1 data BRAM |
| `mxu` | `compute_tile/mxu.sv` | Matmul controller |
| `systolic` | `compute_tile/systolic.sv` | Systolic NxN array |
| `vpu_simd` | `compute_tile/vpu_simd.sv` | SIMD vector unit |

---

## AXI-Lite Register Map

| Offset | Register | Description |
|---|---|---|
| `0x00` | `tpu_mode` | 0=IDLE, 1=WRITE_DEVMEM, 2=READ_DEVMEM, 3=COMPUTE, 4=WRITE_IRAM, 5=DM_TO_L2, 6=L2_TO_DM, 7=L2_TO_L1, 8=L1_TO_L2 |
| `0x04` | `instr_ready` | 1 when TPU is ready for next command |
| `0x08` | `stream_ready` | 1 when DMA stream path is ready |
| `0x0C` | `addr_ram` | Base BRAM/IRAM address (13-bit, used for IRAM writes) |
| `0x10` | `addr_devmem` | Base device memory address (16-bit) |
| `0x14` | `addr_l2` | L2 SRAM base address (15-bit) for DevMem↔L2 and L2↔L1 transfers |
| `0x18` | `length` | Transfer length in elements |

---

## Hardware Constraints

| Constraint | Value | Source of truth |
|------------|-------|-----------------|
| Data BRAM size | 8192 × 32-bit words | blk_mem_gen_0 in l1.sv / blk_mem_models.sv |
| Instr BRAM size | 256 × 64-bit words | blk_mem_gen_1 in blk_mem_models.sv |
| Device memory size | 65536 × 32-bit words | blk_mem_gen_2 in device_mem.sv / blk_mem_models.sv |
| L2 SRAM size | 32768 × 32-bit words | blk_mem_gen_3 in l2_tile.sv / blk_mem_models.sv |
| BRAM read latency | **1 cycle** (registered output) | blk_mem_models.sv `always@(posedge clka)` |
| FIFO depth | 64 entries (parameterized) | fifo4.sv `DEPTH=64` |

### BRAM Latency — Critical Detail

Xilinx Block RAM in registered-output mode (used in synthesis) has **1-cycle latency**:
address captured at posedge → data valid at next posedge.

The behavioral model (`blk_mem_models.sv`) correctly models this as:
```verilog
always @(posedge clka) if (ena) douta <= mem[addra];
```

Any module that reads BRAM must pipeline data signals by exactly 1 cycle, NOT 3.
`tpu_master_axi_stream.v` tracks this with a `bram_reading → bram_data_valid` shift register:
address presented on cycle N → `bram_data_valid` asserts on cycle N+1 → FIFO captures data.

---

## Design Pitfalls

### 1. IDLE→State Reset Signal Pattern (`tpu_slave_axi_stream.v`)

`tpu_slave_axi_stream.v` uses a `reset` register that stays HIGH during IDLE.
The FSM has a **missing `begin`/`end` after `else`**:

```verilog
always @(posedge clk) begin
  if (!ARESETN) begin
    mst_exec_state <= IDLE;
  end
  else              // ← missing begin-end here
    reset <= 1'b0;  // ← this runs ALWAYS (not just in else)
  case (mst_exec_state)
    IDLE: begin
      reset <= 1'b1;  // ← NBA in IDLE overrides the else-reset above
      ...
    end
  endcase
end
```

**Problem:** On IDLE→NextState transition, the IDLE case assigns `reset <= 1'b1` as
an NBA. The block that checks `if(!ARESETN || reset)` fires the reset branch at the FIRST
cycle of NextState, wasting one cycle (e.g., `write_pointer_stream` doesn't increment,
causing the second value to overwrite address 0).

**Fix pattern:** Override `reset` to 0 inside the transition branch — last NBA wins:
```verilog
IDLE: begin
  reset <= 1'b1;
  if (start_condition) begin
    next_state <= TARGET_STATE;
    reset <= 1'b0;  // ← last NBA wins; ensures first TARGET_STATE cycle is productive
  end
end
```

Applied in `tpu_slave_axi_stream.v` line 123: explicit `reset <= 1'b0` on IDLE→WRITE_FIFO.

**Note:** `tpu_master_axi_stream.v` was fully rewritten (2026-02-27) and no longer has this
pattern. It uses a clean 3-state FSM (IDLE → FILL → STREAM) with explicit `fifo_flush`
instead of the `reset` register trick.

### 2. AXI-Stream Write Handshake Timing

`fifo_wren = S_AXIS_TVALID && axis_tready`. The BRAM write (`wea=data_write_en=1`) is
INDEPENDENT of `fifo_wren`. If `write_pointer_stream` doesn't increment when expected,
the next transaction OVERWRITES the previous address. Always verify `write_pointer_stream`
increments on the cycle when `fifo_wren` fires.

---

## Verification Workflow

```bash
# Quick smoke test (PASS/FAIL summary only) — use this first
cd tpu
make smoke-sim          # 3 system tests: data_integrity, device_mem, l2_tile
make smoke-sim-full     # + compute unit tests + compiler smoke

# Unit tests (compute_tile submodules)
cd tpu/verification/compute_tile
make test_<module>     # e.g. make test_mxu, make test_systolic_array

# System integration tests
cd tpu/verification/system
make test_data_integrity_rtl     # System integration integrity test
make test_device_mem             # Device memory read/write integrity
make test_l2_tile                # L2 tile and L1↔L2 hierarchy tests
make test_tpu_compute            # COMPUTE mode end-to-end (modes 3+4)
```

Tests use **cocotb** + **Icarus Verilog**. Results appear in `results.xml`.
BRAM IPs are replaced by `wrappers/blk_mem_models.sv` (1-cycle latency behavioral model).

Use `/tpu-smoke` for quick PASS/FAIL output. Use `/tpu-test` for verbose output when debugging.

**When adding RTL, always add or update a corresponding test.**

---

## Reference Documentation

- ISA specification: `docs/isa.md`
- System architecture & register map: `docs/system.md`
- Host-device programming model (TUDA): `docs/tuda.md`
- Memory hierarchy overview: `docs/memory_hierarchy.md`
- BRAM specs & latency: `docs/bram_specs.md`
- Data movement modes: `docs/data_movement.md`
- Board bug analysis: `docs/board_bugs.md`
- Xilinx block design: `docs/xilinx_block_design.md`
- Verification overview: `docs/verify_overview.md`

---

## Key Design Notes

### Master AXI-Stream Architecture (tpu_master_axi_stream.v)

Rewritten 2026-02-27. Clean 3-state FSM: **IDLE → FILL → STREAM**.

- **FILL** state pre-fills the FWFT FIFO with ~2-4 BRAM words before streaming begins.
  BRAM has 1-cycle latency (address on cycle N → data valid cycle N+1). The FIFO absorbs
  this latency naturally; no startup counter needed.
- **STREAM** continues BRAM reads in parallel with AXI handshakes. Flow-control via
  `fifo_almost_full` prevents overflow. `beats_sent` counter drives TLAST/done.
- **M_AXIS_TKEEP** = all-ones whenever TVALID (required by Xilinx DMA S2MM).
- **FWFT FIFO** (`fifo4.sv`, depth=64): `rd_data` valid combinationally when `!empty`.
  No pipeline stage between FIFO and AXI output. Synchronous `flush` port clears on IDLE.
- **Rising-edge detector** on `read_en` prevents re-trigger race when FSM returns to IDLE
  while `dma_read_en` is still high.

### Architecture Direction (Tensix-Inspired)

**Reference:** Tenstorrent Tensix (system-level; tile-level design differs).

**Memory hierarchy:** L1 (per compute tile, `l1.sv`) ↔ L2 (separate tile) ↔ Device Memory (DDR/HBM).
Data movement across this hierarchy is TPU-initiated via instructions, NOT host-initiated.

- **L1 ↔ L2:** Simple communication instruction (new ISA instruction)
- **L2 ↔ Device Memory:** TMA instruction (address generation, coalescing)
- **Host ↔ Device Memory:** Async memcpy (existing AXI-S or DMA)

**Current state:** Single compute tile with L1. Device memory exists (host DMA target). L2 tile exists (`src/l2_tile/l2_tile.sv`); host-controlled modes 5–8 provide DevMem↔L2↔L1 block copies via addr_l2 (0x14).

**MVP target:** 2×2 mesh of compute tiles + L2 tile underneath, connected via AXI NoC.
Control tile distributes host signals over NoC. All scheduling is static.

**L2 is NOT a second BRAM in `l1.sv`** — it is a separate tile (`src/l2_tile/l2_tile.sv`).

See `PLAN.md` for full task breakdown (P1 = single tile + device memory, P2 = multi-tile mesh).
