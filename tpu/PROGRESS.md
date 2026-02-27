# Mini-TPU RTL: Progress Log

Tracks completed work and current state. Most recent first.
See `PLAN.md` for goals and `CLAUDE.md` for agent working notes / hardware quirks.

---

## 2026-02-27 — Master AXI-Stream + FIFO rewrite + board test (In Progress)

**Status: In Progress — board hang persists**

### RTL rewrite (complete, sim passes)

Rewrote `tpu_master_axi_stream.v` and `fifo4.sv` from scratch per P2.07 plan:

- **`fifo4.sv`**: FWFT synchronous FIFO, depth=64, synchronous `flush` port, `almost_full` signal. Eliminates 1-cycle read pipeline stage — `rd_data` valid combinationally when `!empty`.
- **`tpu_master_axi_stream.v`**: Clean 3-state FSM (IDLE→FILL→STREAM). Removed INIT_COUNTER 32-cycle startup. `reads_issued` / `read_pointer_stream` split for correct BRAM timing. Rising-edge detector on `read_en` prevents re-trigger race.
- **`tpu.sv`**: Added `m00_axis_tkeep` output port (= all-ones whenever TVALID). Removed `C_M00_AXIS_START_COUNT` parameter.
- **TKEEP hypothesis**: The original module lacked `M_AXIS_TKEEP`. Xilinx DMA S2MM requires TKEEP to mark valid data bytes — without it, DMA treats every beat as null → never completes → host `read_bram` hangs.

### Sim regression: all pass

- 9/9 fifo4 unit tests
- 3/3 master_stream unit tests (TKEEP verified = 0xF on all valid beats)
- 4/4 data_integrity boundary tests
- 4/4 tpu_compute tests
- 3/3 smoke-sim

### Board test: HANG PERSISTS

Rebuilt bitstream with TKEEP fix, deployed to Ultra96-v2 (`132.236.59.64`).
Board test result: `read_bram` still hangs on `dma.recvchannel.wait()`.

```
Running 12 test(s)...
^C  (Ctrl-C after hang)
File "runtime/board_tests/test_board.py", line 148, in test_devmem_rw_small
    result = s.tpu.read_bram(0, n)
File "runtime/board_tests/../pynq_host.py", line 196, in read_bram
    self.dma.recvchannel.wait()
```

**TKEEP was NOT the root cause.** The DMA recv channel never completes.

### Next investigation directions for board hang

1. **Vivado IPI wiring**: Verify that `m00_axis_tkeep` is actually connected to the DMA's `s_axis_s2mm_tkeep` in the block design. The repackaged IP may need manual IPI reconnection.
2. **DMA S2MM configuration**: Check if the Xilinx AXI DMA IP is configured in `Direct Register` vs `Scatter-Gather` mode. Confirm `s_axis_s2mm` port width matches 32-bit.
3. **TLAST timing**: Board DMA requires TLAST to fire exactly once at end of transfer. If TLAST fires early or never, DMA hangs.
4. **ILA/VIO debug**: Add ILA probes on `m00_axis_tvalid`, `m00_axis_tready`, `m00_axis_tlast`, `m00_axis_tkeep` to observe actual AXI-Stream handshake on fabric.
5. **Clock domain**: Verify `M_AXIS_ACLK` is the same clock as the DMA S2MM interface clock.
6. **PYNQ DMA buffer alignment**: `dma.recvchannel.transfer(buf)` may require physically contiguous, cache-coherent buffer. Check `allocate()` vs `xlnk.cma_array()`.

### Documentation cleanup (complete)

Fixed 10 stale references across CLAUDE.md, PROGRESS.md, README.md, and 3 Makefiles.

### Pending items (deferred to next session)

- [ ] Consolidate `runtime/board_tests/` under `tpu/` directory
- [ ] Create `/tpu-board-align` skill (sim→board→diagnose→align cycle)
- [ ] Create `/tpu-deploy` skill (`make bitstream → make tpu → make board-test` pipeline)

---

## 2026-02-27 — board-test deploy fix + P1.7-4 cocotbext-axi BFMs (Complete)

**Status: Complete**

### board-test Makefile fix (`tpu/Makefile`)

- **Root cause:** `board-test` deployed only `pynq_host.py` + `__init__.py`. `runtime/__init__.py` imports `allocator.py` and `device.py` at module load time — both absent on board — causing `ImportError` on any `from runtime.* import` call. Symptom: hung `read_bram` when running `smoke_board.tu` / `dummy_test.tu` on board.
- **Fix:** `board-test` now does `cp -r runtime/.` (full directory, stripping `__pycache__`/`.pyc`). `smoke-board` PROGRAM var fixed: was `mlp.tu` (wrong), now `smoke_board.tu`. New `board-tests` target deploys full runtime and runs `runtime/board_tests/test_board.py` on the board.
- **Usage:** `make board-tests [BOARD_TEST_ARGS="--test devmem_rw_small --verbose"]`
- **Commit:** `20c35ae`

### P1.7-4: cocotbext-axi BFM integration

- **`verification/system/test_tpu.py`:** `TpuRtlDriver.write_bram()` replaced with `AXIStreamSource.send(AxiStreamFrame(bytes))` — packs float32 array into a byte frame, BFM handles TVALID/TREADY/TLAST handshaking internally. `read_bram()` replaced with `AXIStreamSink.recv()` — BFM holds TREADY high, accumulates beats, returns frame on TLAST. 3–5× fewer VPI crossings per transfer.
- **`verification/system/Makefile`:** Added `CONDA_PYTHON` (resolves minitpu conda env Python via `conda run -n minitpu which python3`). Added `CONDA_SITE_PKGS` injected into `PYTHONPATH` so cocotbext-axi (installed only in the conda env) is visible when cocotb embeds Python via the VPI mechanism. `COCOTB_LIBS` changed to `:=` (immediate expand) so it uses CONDA_PYTHON rather than system python3.
- **Test result:** All 4 boundary tests pass (N=8, N=9, N=16, known values); 3/3 smoke sim pass; 4/4 tpu_compute tests pass.
- **Commit:** `9e82100`

**P1.7 all 6 sub-tasks now complete.** Next priorities: P2.1 (AXI NoC infrastructure) or P1.4 board +2 shift root cause (requires hardware).

---

## 2026-02-27 — P2.08: Separate DMA and Compute FSMs (Complete)

**Status: Complete**

Factored the monolithic `tpu.sv` FSM into three independent sub-FSMs and a thin concurrent arbiter. All three run simultaneously when their respective BRAM ports are not in conflict.

### Architecture

- `dma_engine.sv` (new): modes 1/2/4/5/6 — owns AXI-Stream path + device_mem Port A
- `compute_ctrl.sv` (new): mode 3 — compute tile start/done handshake (2-state FSM)
- `l2_ctrl.sv` (new): modes 7/8 — L2 Port A + L1 DMA port; 1-cycle BRAM pipeline
- `tpu.sv` (refactored): doorbell arbiter dispatches descriptors to disjoint sub-FSMs; `instr_ready = !dma_running && !compute_running && !l2_running`

### Concurrent execution

BRAM port ownership is fully disjoint:
- device_mem Port A → dma_engine only
- L2 Port A → l2_ctrl only; L2 Port B → tma_engine (inside l2_tile) only
- L1 Port A → l2_ctrl DMA; L1 Port B → tensorcore (compute_ctrl)

Verified: `test_dma_compute_overlap` fires mode-3 then mode-1 back-to-back without waiting for `instr_ready` between them. Both sub-FSMs run concurrently. Verified correct output for both DMA write and compute result.

### Board driver update

`runtime/pynq_host.py` fully rewritten to use P1.8 doorbell protocol throughout. All methods now write `(mode | 0x10)` — no trailing IDLE write. Added `devmem_to_l2`, `l2_to_devmem`, `l2_to_l1`, `l1_to_l2` methods. IRAM `write_instructions` default `base_addr=1` with full docstring explaining the timing workaround.

### Board test suite (new)

`runtime/board_tests/test_board.py` — 12 offline board tests:

| # | Test | What it covers |
|---|------|----------------|
| 1 | `devmem_rw_small` | 8-word DevMem roundtrip |
| 2 | `devmem_rw_large` | 256-word DevMem roundtrip |
| 3 | `devmem_base_offset` | non-zero base address |
| 4 | `devmem_multi_region` | two regions, no aliasing |
| 5 | `devmem_boundary_8` | N=FIFO depth; Bug A/B regression |
| 6 | `devmem_boundary_9` | N=FIFO+1; drain transition |
| 7 | `devmem_known_values` | bit-exact float pattern |
| 8 | `deadbeef` | 0xDEADBEEF bit-exact roundtrip |
| 9 | `l2_dm_roundtrip` | DevMem→L2→DevMem |
| 10 | `l2_l1_roundtrip` | DevMem→L2→L1→L2→DevMem |
| 11 | `hierarchy_pipeline` | Full hierarchy + identity kernel |
| 12 | `vadd_kernel` | VADD kernel end-to-end on board |

`runtime/board_tests/diagnose_board.py` — hardware diagnostic probe: AXI-Lite register dump, DMA channel status, overlay IP list, shift-bug probe.

### Verification coverage

`tpu/docs/verification.md` (1007 lines): full line/path coverage for all 22 RTL modules under `tpu/src/`. Summary table, known issues, concurrent execution documentation.

### Regression results

| Suite | Tests | Result |
|-------|-------|--------|
| `test_data_integrity_rtl` | 4 | PASS |
| `test_device_mem` | 3 | PASS |
| `test_l2_tile` | 4 | PASS |
| `test_tpu_compute` | 4 (3 prior + overlap) | PASS |

Files changed: `src/system/tpu.sv` (refactored), `src/system/dma_engine.sv` (new), `src/system/compute_ctrl.sv` (new), `src/system/l2_ctrl.sv` (new), `verification/system/test_tpu_compute.py`, `verification/system/Makefile`, `docs/verification.md`, `runtime/pynq_host.py` (full rewrite), `runtime/board_tests/test_board.py` (new), `runtime/board_tests/diagnose_board.py` (new)

---

## 2026-02-27 — P1.8: Doorbell-Based Descriptor DMA (Complete)

**Status: Complete**

Implemented doorbell mechanism to eliminate `tpu_mode == 0` polling loop in `ST_WAIT_DONE` and reduce VPI crossing overhead per transfer.

### Design

- `slv_reg0[4]` = doorbell bit. Host writes `mode | 0x10` to arm mode and assert doorbell atomically in one AXI-Lite write.
- `tpu_slave_axi_lite.v`: added `doorbell_out` output (= `slv_reg0[4]`), `doorbell_clear` input (1-cycle pulse from tpu.sv to clear bit 4 on acceptance). Doorbell auto-clear placed inside the main write `always` block — "last NBA wins" semantics correctly override host writes.
- `tpu.sv`: added `doorbell` wire, `doorbell_clear` reg (pulse), `latched_mode` reg. `ST_IDLE` now gates on `doorbell` (not `tpu_mode`). On doorbell: latches `tpu_mode[3:0]` → `latched_mode`, pulses `doorbell_clear`, dispatches. `ST_EXEC_WRITE` uses `latched_mode` (not live `tpu_mode`). `ST_WAIT_DONE` unconditionally returns to `ST_IDLE` — safe because doorbell is cleared before FSM leaves `ST_IDLE`, so no re-trigger.
- Driver: `test_tpu.py` and `test_tpu_compute.py` updated — all methods use `write_axi_lite(0x00, mode | 0x10)`. Trailing `write_axi_lite(0x00, 0)` IDLE writes removed.

### Regression results

| Suite | Tests | Result |
|-------|-------|--------|
| `test_data_integrity_rtl` | 4 | PASS |
| `test_device_mem` | 3 | PASS |
| `test_l2_tile` | 4 | PASS |

Files changed: `src/system/tpu_slave_axi_lite.v`, `src/system/tpu.sv`, `verification/system/test_tpu.py`, `verification/system/test_tpu_compute.py`, `PLAN.md`, `PROGRESS.md`

---

## 2026-02-27 — P1.5/P1.6/P1.7/P2.07 Parallel Task Completion

**Status: Complete**

All planned tasks resolved in parallel via four isolated git worktree agents. Baseline: 3/3 smoke tests passing throughout.

### P1.5: TMA Instruction End-to-End Test (RESOLVED)

RTL was already fully implemented (`decoder.sv` MODE=2, `tensorcore.sv` EXEC_TMA/WAIT_TMA, `tma_engine.sv`, `l2_tile.sv`, `tpu.sv` wiring). Added missing system-level test:
- `verification/system/test_tpu_compute.py`: added `encode_tma_instr()` helper and `test_tma_instruction_in_kernel` test
- Test flow: host→DevMem[32:39] → TMA kernel (MODE=2, dm_base=32, l2_base=0, len=8) → L2→L1→L2→DevMem[100:107]→host; verify [10.0..17.0]
- Result: TESTS=3 PASS=3 FAIL=0 (identity kernel, VADD kernel, TMA kernel)
- PLAN.md: P1.5 marked RESOLVED

### P1.6: ISA Documentation Overhaul (RESOLVED)

- `docs/isa.md`: MODE=2 changed from RESERVED→TMA; added full TMA section (field table, semantics, constraints, example, mnemonic `tma <dir> <dm_base> <l2_base> <len>`)
- `docs/system.md`: added TMA instruction note after mode table
- PLAN.md: P1.6 marked RESOLVED

### P1.7-5: Unit-Level AXI-Stream Tests (DONE)

New standalone unit tests compile only the DUT (not the full 20-file tpu top):
- `verification/system/test_slave_stream.py`: 3 tests for `tpu_slave_axi_stream` (n=1, n=4, n=8 Bug A regression) — TESTS=3 PASS=3 FAIL=0
- `verification/system/test_master_stream.py`: 3 tests for `tpu_master_axi_stream` + `fifo4` (n=1, n=4, n=8) — TESTS=3 PASS=3 FAIL=0
- `verification/system/Makefile`: added `test_slave_stream` and `test_master_stream` targets
- Sim time: ~210ns and ~1230ns respectively (~10× faster compile than full system)
- Key finding: slave `C_S_AXIS_TDATA_WIDTH=64` so tdata is 64-bit; data_to_bram is lower 32 bits

### P2.07: Parameterize fifo4 DEPTH (RESOLVED)

- `src/system/fifo4.sv`: added `DEPTH=8` parameter; derived `PTR_W = $clog2(DEPTH)+1`; all hardcoded indices/widths replaced
- `src/system/tpu_master_axi_stream.v`: added `localparam FIFO_DEPTH=8`; instantiation uses `#(.WIDTH(32), .DEPTH(FIFO_DEPTH))`
- No functional change at DEPTH=8; all 7 fifo4 unit tests pass; smoke 3/3 pass

### P1.7-2: SIM= Makefile selector (DONE)

- `verification/system/Makefile`: added `SIM ?= icarus` variable block with `ifeq ($(SIM),verilator)` conditional; documented alongside TESTCASE=/VCD= comment block

### Files changed
`verification/system/test_tpu_compute.py`, `verification/system/test_slave_stream.py` (new), `verification/system/test_master_stream.py` (new), `verification/system/Makefile`, `src/system/fifo4.sv`, `src/system/tpu_master_axi_stream.v`, `docs/isa.md`, `docs/system.md`, `PLAN.md`

### Commits
- `341da41` doc) P1.6 ISA documentation overhaul
- `8432201` feat) P2.07 + P1.7-2 — parameterize FIFO depth, add SIM= Makefile selector
- `4e3ad62` feat) P1.5 TMA instruction — add end-to-end system test + mark RESOLVED
- `c1655f4` feat) P1.7-5 unit stream tests — test_slave_stream + test_master_stream

---

## 2026-02-27 — Sim Infrastructure + DMA Bug B Reanalysis

**Status: Complete**

### Bug B reanalysis

The `!fifo_empty` gate on `M_AXIS_TVALID` (added 2026-02-26) was **wrong** — it drops the last word because `fifo_empty` and `rd_data`/`valid_d1` update in the same NBA cycle. The last valid `rd_data` appears exactly when `fifo_empty` goes HIGH after the final `rptr` NBA.

**Finding: Bug B does NOT exist in RTL.** `valid_d1` and `rd_data` are inherently aligned (both 1-cycle delayed from `rd_en`), so no duplicate occurs. Reverted to `assign M_AXIS_TVALID = valid_d1`. All 4 boundary tests (N=8, N=9, N=16, known values) pass.

The board +2 shift has a different root cause. Suspect list:
1. BRAM output register: Vivado IP cache may retain 2-cycle config despite TCL change
2. PS DMA timing: Zynq `xlnk.cma_array` handshake differs from cocotb
3. Clock domain: three separate cocotb clocks vs. one hardware clock

### Sim infrastructure changes

1. **`environment.yml`** (new): conda env spec — python 3.9, cocotb>=2.0, cocotbext-axi, numpy
2. **`tpu/Makefile`**: added `make setup` target for conda env creation
3. **`test_tpu.py`**: dropped N=64 from `test_data_integrity` (was ~80% of sim cost)
4. **System `Makefile`**: added `TESTCASE=` (→ `COCOTB_TESTCASE`) and `VCD=1` (→ `-DVCD_DUMP`) selectors
5. **`blk_mem_models.sv`**: added conditional `vcd_dump` module (`ifdef VCD_DUMP`)

### Sim performance

| Before | After |
|--------|-------|
| ~4,622 cycles/sec, N=64 test alone ~80 min | ~40,000 ns/s, full 4-test suite in 0.19s |

### PLAN.md updates

Added new P-tasks: P1.7 (Verification Infrastructure Overhaul), P1.8 (Descriptor-Based DMA Engine), P2.07 (Deepen AXI-Stream FIFO), P2.08 (Separate DMA and Compute FSMs).

### Regression results

| Suite | Tests | Result |
|-------|-------|--------|
| `test_data_integrity_rtl` | 4 | PASS |
| `test_device_mem` | 3 | PASS |
| `test_l2_tile` | 4 | PASS |

Files changed: `environment.yml`, `tpu/Makefile`, `tpu/verification/system/Makefile`, `tpu/verification/system/test_tpu.py`, `tpu/src/system/tpu_master_axi_stream.v`, `tpu/verification/compute_tile/wrappers/blk_mem_models.sv`, `tpu/PLAN.md`, `tpu/PROGRESS.md`

---

## 2026-02-26 — P1.4: Board Smoke Test Debugging (In Progress)

**Status: Root cause identified, fix pending**

Investigated board DEADBEEF roundtrip failure. Simulation passes. Board shows corrupted DMA reads.

### Work completed this session

**1. FallingEdge VPI fix (`tpu/verification/l2_tile/test_tma.py`)**
Two TMA tests (`test_host_dm_to_l2`, `test_tma_dm_to_l2`) were failing with wrong data (0 instead of expected values). Root cause: `dut.dm_dout.value = X` after `await RisingEdge` fires in the ReadWrite phase, AFTER the BRAM's `always @(posedge)` already sampled `sram_din_b=0`. Fix: drive `dm_dout` at `FallingEdge` (midpoint), giving VPI a full half-period to propagate before the next posedge. All 5 TMA tests now pass (TESTS=5 PASS=5 FAIL=0).

**2. Board driver fixes (`runtime/pynq_host.py`)**
- Added `addr_devmem: 0x10` and `addr_l2: 0x14` to `REG_ADDR` (were missing after P1.1 moved device memory from 0x0C to 0x10)
- Fixed `write_bram`/`read_bram` to use `REG_ADDR["addr_devmem"]` instead of `REG_ADDR["addr_ram"]`
- Fixed `read_bram`: `recv_channel.transfer()` now called before `tpu_mode = READ_BRAM` (was reversed, risking DMA miss)

**3. smoke_board.tu import fix (`demos/programs/smoke_board.tu`)**
`runtime.tuda` import chain not deployed to board. Rewrote to import `TpuDriver` directly from `runtime.pynq_host`.

**4. Synthesis (`tpu/scripts/package_tpu_ip.tcl`, `tpu/Makefile`)**
- Added `blk_mem_gen_2` (device memory) and `blk_mem_gen_3` (L2 SRAM) to IP packaging TCL
- Added L2 tile RTL (`src/l2_tile/*.sv`) to Vivado IP packaging command
- Uncommented `PROJ_NAME ?= minitpu`
- Bitstream built: `minitpu.bit` (5.4 MB), timing slack 0.216 ns

**5. BRAM output register fix (`tpu/scripts/package_tpu_ip.tcl`)**
All 4 BRAMs had `Register_PortA/B_Output_of_Memory_Primitives {true}` (2-cycle hardware latency) while simulation uses 1-cycle behavioral model. Changed all to `{false}`. Requires bitstream rebuild. Commit: `9d6a58b`.

**6. Memory hierarchy documentation (`tpu/docs/memory_hierarchy.md`)**
Full reference document covering all 4 BRAMs, all 8 DMA modes, Mode 2 cycle-by-cycle timing, and board bug analysis.

### Board test results

First test (16 words): `result[i] = data[i+2]` — clean +2 shift.
Second test (31 words, after pynq_host.py fix): same +2 shift plus `data[8]` duplicated:
```
[6]:  got 0x08   (expected 0x06)
[7]:  got 0x08   ← SAME AS [6]: duplicate
[30]: got 0x1F   ← out-of-range repeat
```

### Root cause identified: two compounding DMA bugs

**Bug A — `tpu_slave_axi_stream.v` write pointer stall:**
The IDLE→WRITE_FIFO reset stall (CLAUDE.md Design Pitfall §1) fires on the first WRITE_FIFO cycle. `write_pointer_stream` is held at 0 while `wea` (BRAM write enable) is already asserted — both `data[0]` and `data[1]` write to BRAM address 0. `data[0]` is permanently overwritten. Effective stored content is `[data[1], data[2], ..., data[N-1], garbage]`.

**Bug B — `tpu_master_axi_stream.v` FIFO registered-read boundary duplicate:**
`fifo4` uses registered (clocked) read output. At the FIFO drain boundary, `rd_data` holds the last value for one extra cycle after `fifo_empty` goes high. `axis_tvalid` deasserts one cycle late (combinatorial from `!fifo_empty`, but empty is itself registered). The DMA sees the last FIFO word twice.

Net effect: write loses 1 word (+1 shift), read repeats 1 word (net +1 shift) = +2 total.

### Fixes needed (P1.4)

| Bug | File | Fix |
|-----|------|-----|
| A: slave write stall | `tpu_slave_axi_stream.v` | Gate BRAM `wea` on `fifo_wren` (AXI handshake), not just `data_write_en` |
| B: master FIFO boundary duplicate | `tpu_master_axi_stream.v` | Gate `axis_tvalid` using `fifo_one_left` (same pattern as `tlast`) |

Both fixes require RTL sim regression after change. Bitstream rebuild required for board validation.

See `tpu/docs/memory_hierarchy.md` §6–7 for full analysis.

---

## 2026-02-25 — P1.2 + P1.3: L2 Tile and Host-Controlled Memory Hierarchy (Complete)

**Status: Complete**

Implemented L2 shared SRAM tile with host-controlled block transfer modes, completing the DevMem↔L2↔L1 data path.

Changes:
- `verification/compute_tile/wrappers/blk_mem_models.sv`: added `blk_mem_gen_3` (32768×32 dual-port behavioral SRAM, 15-bit address)
- `src/l2_tile/l2_tile.sv` (new): L2 tile top with blk_mem_gen_3 + DevMem↔L2 pipelined burst FSM; Port A = compute tile, Port B = device memory facing
- `src/system/tpu.sv`: extended tpu_mode to 4 bits; added modes 5–8 (DM_TO_L2, L2_TO_DM, L2_TO_L1, L1_TO_L2); added l2_tile instantiation; connected device_mem Port B to l2_tile dm_ ports; added addr_l2 from slv_reg5_bus[14:0] (register 0x14); counter-based L2↔L1 FSM using combinational address wires (avoids extra BRAM latency cycle)
- `verification/system/test_tpu.py`: added devmem_to_l2, l2_to_devmem, l2_to_l1, l1_to_l2 driver methods
- `verification/system/test_l2_tile.py` (new): 4 tests — DM↔L2 round-trip, full DM→L2→L1→L2→DM pipeline, multiple sizes (16/64/128), base address isolation
- `verification/system/Makefile`: added l2_tile.sv to SRC_TPU, added test_l2_tile target

Test results:
- `make test_data_integrity_rtl` → **TESTS=1 PASS=1 FAIL=0** ✓
- `make test_device_mem` → **TESTS=3 PASS=3 FAIL=0** ✓
- `make test_l2_tile` → **TESTS=4 PASS=4 FAIL=0** ✓

Design note: Simplified from ISA instruction (PLAN.md P1.3 spec) to host-controlled modes. Avoids decoder/tensorcore changes for the prototype. In-kernel L1↔L2 movement via ISA remains future work.

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
| Subnormals (<1.18e-38) cause bus errors | FP32 units | P3 |
| MXU per-element stall (no pipelined burst) | `mxu.sv` | P3 |
| Board +2 shift (requires hardware investigation) | DMA path | P1 |

Resolved issues (removed from table):
- Scalar VPU ops → RESOLVED in P2.06 (2026-02-27)
- MXU ~33% peak → PARTIALLY RESOLVED in P2.05 (MEM_LATENCY 3→1, 3× speedup; true burst is P3)
- DMA off-by-one → likely resolved by master stream rewrite (2026-02-27); needs board verification
