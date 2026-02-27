# Mini-TPU Verification Coverage

> Living document — last updated 2026-02-27.
> Covers all RTL modules under `tpu/src/`. See `PLAN.md` for the task backlog and `PROGRESS.md` for recent changes.
> Reference: `tpu/docs/system.md` (register map), `tpu/docs/isa.md` (instruction set).

---

## Contents

1. [RTL Module Coverage](#rtl-module-coverage)
   - [src/system/tpu.sv](#srcsystemtpusv)
   - [src/system/dma_engine.sv](#srcsystemdma_enginesv)
   - [src/system/compute_ctrl.sv](#srcsystemcompute_ctrlsv)
   - [src/system/l2_ctrl.sv](#srcsysteml2_ctrlsv)
   - [src/system/tpu_slave_axi_lite.v](#srcsystemtpu_slave_axi_litev)
   - [src/system/tpu_slave_axi_stream.v](#srcsystemtpu_slave_axi_streamv)
   - [src/system/tpu_master_axi_stream.v](#srcsystemtpu_master_axi_streamv)
   - [src/system/fifo4.sv](#srcsystemfifo4sv)
   - [src/system/device_mem.sv](#srcsystemdevice_memsv)
   - [src/l2_tile/l2_tile.sv](#srcl2_tilel2_tilesv)
   - [src/l2_tile/tma_engine.sv](#srcl2_tiletma_enginesv)
   - [src/compute_tile/compute_tile.sv](#srccompute_tilecompute_tilesv)
   - [src/compute_tile/tensorcore.sv](#srccompute_tiletensorcoresv)
   - [src/compute_tile/decoder.sv](#srccompute_tiledecodersv)
   - [src/compute_tile/l1.sv](#srccompute_tilel1sv)
   - [src/compute_tile/mxu.sv](#srccompute_tilemxusv)
   - [src/compute_tile/systolic.sv + pe.sv](#srccompute_tilesystolicsv--pesv)
   - [src/compute_tile/vpu_simd.sv](#srccompute_tilevpu_simdsv)
   - [src/compute_tile/vpu_op.sv](#srccompute_tilevpu_opsv)
   - [src/compute_tile/vec_regfile.sv](#srccompute_tilevec_regfilesv)
   - [src/compute_tile/fp32_add.sv + fp32_mul.sv](#srccompute_tilefp32_addsv--fp32_mulsv)
   - [src/compute_tile/pc.sv](#srccompute_tilepcsv)
2. [Summary Table: Tests to Modules](#summary-table-tests-to-modules)
3. [Known Issues](#known-issues)
4. [Concurrent Execution (P2.08)](#concurrent-execution-p208)
5. [Coverage Gaps Summary](#coverage-gaps-summary)

---

## RTL Module Coverage

### `src/system/tpu.sv`

**Role:** Top-level TPU module. Implements a thin concurrent arbiter that dispatches incoming doorbell-triggered commands to three independent sub-FSMs: `dma_engine` (modes 1/2/4/5/6), `compute_ctrl` (mode 3), and `l2_ctrl` (modes 7/8). Instantiates all structural sub-modules including the AXI slaves/master, memory tiles, and the compute tile. Manages `instr_ready` and `stream_ready` status signals exposed over AXI-Lite.

**Test files:**
- `tpu/verification/system/test_tpu.py` — `TpuRtlDriver` base driver used by all system tests
- `tpu/verification/system/test_data_integrity.py` — exercises DMA write/read (modes 1 and 2)
- `tpu/verification/system/test_device_mem.py` — exercises modes 1 and 2 at various sizes and offsets
- `tpu/verification/system/test_l2_tile.py` — exercises modes 1/2/5/6/7/8
- `tpu/verification/system/test_tpu_compute.py` — exercises all 8 modes (1/2/3/4/5/6/7/8)

**Test functions exercising this module:**

| Test function | Test file | Modes covered |
|---|---|---|
| `test_data_integrity` | `test_tpu.py` | 1 (write), 2 (read) |
| `test_boundary_n8` | `test_tpu.py` | 1, 2 (N=8 FIFO depth boundary) |
| `test_boundary_n9` | `test_tpu.py` | 1, 2 (N=9 prefill-to-steady-state) |
| `test_boundary_n16` | `test_tpu.py` | 1, 2 (N=16 standard size) |
| `test_devmem_write_read_integrity` | `test_device_mem.py` | 1, 2 |
| `test_devmem_multiple_sizes` | `test_device_mem.py` | 1, 2 (sizes 16, 64, 256) |
| `test_devmem_base_addr_offset` | `test_device_mem.py` | 1, 2 (addr=0x100) |
| `test_dm_l2_roundtrip` | `test_l2_tile.py` | 1, 5, 6, 2 |
| `test_dm_l2_l1_l2_dm_roundtrip` | `test_l2_tile.py` | 1, 5, 7, 8, 6, 2 |
| `test_l2_l1_sizes` | `test_l2_tile.py` | 1, 5, 7, 8, 6, 2 |
| `test_l2_l1_base_addr_offset` | `test_l2_tile.py` | 1, 5, 7, 8, 6, 2 |
| `test_compute_identity_kernel` | `test_tpu_compute.py` | 1, 5, 7, 4, 3, 8, 6, 2 |
| `test_compute_vadd_kernel` | `test_tpu_compute.py` | 1, 5, 7, 4, 3, 8, 6, 2 |
| `test_tma_instruction_in_kernel` | `test_tpu_compute.py` | 1, 4, 3, 7, 8, 6, 2 |
| `test_dma_compute_overlap` | `test_tpu_compute.py` | 1, 5, 7, 4, 3+1 concurrent, 8, 6, 2 |

**FSM states / behavioral paths covered:**
- Arbiter dispatch to `dma_engine` for modes 1, 2, 4, 5, 6
- Arbiter dispatch to `compute_ctrl` for mode 3
- Arbiter dispatch to `l2_ctrl` for modes 7, 8
- `instr_ready` de-assertion when any sub-FSM starts; re-assertion when all sub-FSMs idle
- `stream_ready` asserted by `dma_engine` when AXI-Stream write path is open
- Concurrent dispatch: mode 3 and mode 1 running simultaneously (`test_dma_compute_overlap`)
- Doorbell protocol: combined mode+doorbell write in a single AXI-Lite write (bit 4)

**Known coverage gaps:**
- Concurrent dispatch of `l2_ctrl` (modes 7/8) with `dma_engine` or `compute_ctrl` — only DMA+compute overlap is tested
- Arbiter behavior when a second doorbell arrives while same sub-FSM is already running (software contract violation)
- Mode 0 (IDLE explicit write) is not tested as a distinct command
- Invalid mode values (> 8) — RTL behavior undefined

---

### `src/system/dma_engine.sv`

**Role:** DMA/host-transfer sub-FSM introduced in P2.08. Owns AXI-Stream slave control (modes 1 and 4: write to device memory or IRAM), AXI-Stream master control (mode 2: read from device memory), and L2 host-controlled block transfers via `tma_engine` (modes 5/6: DM↔L2). Manages the IRAM address counter for mode 4. Asserts `stream_ready` when the AXI-Stream write path is open. Drives `done` as a 1-cycle pulse on transfer completion.

**Test files:**
- `tpu/verification/system/test_data_integrity.py` — modes 1 and 2
- `tpu/verification/system/test_device_mem.py` — modes 1 and 2
- `tpu/verification/system/test_l2_tile.py` — modes 5 and 6
- `tpu/verification/system/test_tpu_compute.py` — modes 4, 5, 6, and concurrent mode 1 with mode 3

**Test functions exercising this module:**

| Test function | Test file | dma_engine state(s) exercised |
|---|---|---|
| `test_data_integrity` | `test_tpu.py` | DE_IDLE → DE_WRITE (WR_DEVMEM) → DE_READ |
| `test_boundary_n8` | `test_tpu.py` | DE_WRITE (WR_DEVMEM), DE_READ at N=8 |
| `test_boundary_n9` | `test_tpu.py` | DE_WRITE (WR_DEVMEM), DE_READ at N=9 |
| `test_boundary_n16` | `test_tpu.py` | DE_WRITE (WR_DEVMEM), DE_READ at N=16 |
| `test_devmem_write_read_integrity` | `test_device_mem.py` | DE_WRITE (WR_DEVMEM), DE_READ |
| `test_devmem_multiple_sizes` | `test_device_mem.py` | DE_WRITE, DE_READ (sizes 16, 64, 256) |
| `test_devmem_base_addr_offset` | `test_device_mem.py` | DE_WRITE, DE_READ (addr=0x100) |
| `test_dm_l2_roundtrip` | `test_l2_tile.py` | DE_DM2L2, DE_L22DM |
| `test_dm_l2_l1_l2_dm_roundtrip` | `test_l2_tile.py` | DE_DM2L2, DE_L22DM |
| `test_l2_l1_sizes` | `test_l2_tile.py` | DE_DM2L2, DE_L22DM (sizes 16, 64, 128) |
| `test_l2_l1_base_addr_offset` | `test_l2_tile.py` | DE_DM2L2, DE_L22DM (addr offsets) |
| `test_compute_identity_kernel` | `test_tpu_compute.py` | DE_WRITE (WR_IRAM), DE_DM2L2, DE_L22DM |
| `test_compute_vadd_kernel` | `test_tpu_compute.py` | DE_WRITE (WR_IRAM), DE_DM2L2, DE_L22DM |
| `test_tma_instruction_in_kernel` | `test_tpu_compute.py` | DE_WRITE (WR_IRAM), DE_L22DM |
| `test_dma_compute_overlap` | `test_tpu_compute.py` | DE_WRITE (WR_DEVMEM) concurrent with compute_ctrl |

**FSM states covered:**
- `DE_IDLE` — entry and exit via doorbell dispatch
- `DE_WRITE` / `WR_DEVMEM` sub-path — host → device memory via AXI-Stream slave
- `DE_WRITE` / `WR_IRAM` sub-path — host → IRAM via AXI-Stream slave (mode 4)
- `DE_READ` — device memory → host via AXI-Stream master (mode 2)
- `DE_DM2L2` — device memory to L2 block copy (mode 5)
- `DE_L22DM` — L2 to device memory block copy (mode 6)

**Known coverage gaps:**
- `DE_WRITE` WR_IRAM: IRAM write across page boundaries (addr_ram > 0 initial non-zero base not tested beyond the workaround value of 1)
- Simultaneous `dma_engine` + `l2_ctrl` concurrent execution not tested
- `done` pulse width and timing relative to `instr_ready` re-assertion not explicitly asserted in any test

---

### `src/system/compute_ctrl.sv`

**Role:** Compute dispatch sub-FSM introduced in P2.08. Owns the compute tile start/done handshake for mode 3 (COMPUTE). Receives a 1-cycle `start` pulse from the arbiter, fires `start_compute_tile`, waits for `compute_tile_done`, and emits a 1-cycle `done` pulse. Contains only two states: `CC_IDLE` and `CC_RUNNING`.

**Test files:**
- `tpu/verification/system/test_tpu_compute.py` — all four test functions exercise this module

**Test functions exercising this module:**

| Test function | Kernel executed | States visited |
|---|---|---|
| `test_compute_identity_kernel` | VLOAD V0 + VSTORE V0 + HALT | CC_IDLE → CC_RUNNING → CC_IDLE |
| `test_compute_vadd_kernel` | VLOAD V0 + VLOAD V1 + VCOMPUTE V2=V0+V1 + VSTORE V2 + HALT | CC_IDLE → CC_RUNNING → CC_IDLE |
| `test_tma_instruction_in_kernel` | TMA(DM→L2) + HALT | CC_IDLE → CC_RUNNING → CC_IDLE |
| `test_dma_compute_overlap` | Identity kernel (concurrent with dma_engine mode 1) | CC_RUNNING while dma_engine DE_WRITE runs |

**FSM states covered:**
- `CC_IDLE` — reset state and idle between operations
- `CC_RUNNING` — from `start_compute_tile` assertion until `compute_tile_done`

**Known coverage gaps:**
- `CC_RUNNING` with long-running multi-instruction programs that take >5000 cycles — timeout behavior not tested
- No test verifies behavior if `start` is pulsed while `CC_RUNNING` (arbiter enforces this software contract, but `compute_ctrl` itself has no guard)

---

### `src/system/l2_ctrl.sv`

**Role:** L2↔L1 burst transfer sub-FSM introduced in P2.08. Owns L2 tile Port A and the L1 DMA port (Port A of compute tile L1 BRAM). Implements burst block copies in both directions: mode 7 (L2→L1) and mode 8 (L1→L2). Handles the 1-cycle registered BRAM read latency by pipelining addresses ahead of data. States: `LC_IDLE`, `LC_L22L1`, `LC_L12L2`.

**Test files:**
- `tpu/verification/system/test_l2_tile.py` — all four tests exercise L2↔L1 paths
- `tpu/verification/system/test_tpu_compute.py` — exercises modes 7 and 8 as part of full compute flow

**Test functions exercising this module:**

| Test function | Test file | l2_ctrl state(s) exercised |
|---|---|---|
| `test_dm_l2_roundtrip` | `test_l2_tile.py` | LC_IDLE only (this test uses modes 5/6 which are dma_engine) |
| `test_dm_l2_l1_l2_dm_roundtrip` | `test_l2_tile.py` | LC_IDLE → LC_L22L1 → LC_IDLE → LC_L12L2 → LC_IDLE |
| `test_l2_l1_sizes` | `test_l2_tile.py` | LC_L22L1, LC_L12L2 (sizes 16, 64, 128) |
| `test_l2_l1_base_addr_offset` | `test_l2_tile.py` | LC_L22L1, LC_L12L2 (non-zero L2 and L1 base offsets) |
| `test_compute_identity_kernel` | `test_tpu_compute.py` | LC_L22L1 (mode 7), LC_L12L2 (mode 8) |
| `test_compute_vadd_kernel` | `test_tpu_compute.py` | LC_L22L1 (twice), LC_L12L2 |
| `test_tma_instruction_in_kernel` | `test_tpu_compute.py` | LC_L22L1, LC_L12L2 |
| `test_dma_compute_overlap` | `test_tpu_compute.py` | LC_L22L1, LC_L12L2 (sequential, not concurrent with other sub-FSMs) |

**FSM states covered:**
- `LC_IDLE` — entry, exit, and inter-operation idle
- `LC_L22L1` — L2 read followed by L1 write, 1-cycle pipeline delay handled
- `LC_L12L2` — L1 read followed by L2 write, 1-cycle pipeline delay handled
- Both modes 7 and 8 covered at sizes 8, 16, 64, and 128 words
- Non-zero L2 base addresses (0x100, 0x200, 0x400, 0x1000) covered
- Non-zero L1 base addresses (0, 8, 16) covered

**Known coverage gaps:**
- `LC_L22L1` concurrent with `dma_engine` or `compute_ctrl` — only sequential ordering is tested
- Transfer sizes larger than 128 words not tested
- L1 DMA port write pointer wrapping past the BRAM boundary not tested

---

### `src/system/tpu_slave_axi_lite.v`

**Role:** AXI-Lite register slave. Exposes the TPU control register file to the host. Handles all AXI-Lite write (AWVALID/WVALID/BVALID handshake) and read (ARVALID/RVALID handshake) cycles. Implements seven registers:

| Offset | Register | Description |
|---|---|---|
| `0x00` | `tpu_mode` | Mode + doorbell (bit 4) |
| `0x04` | `instr_ready` | 1 when all sub-FSMs are idle |
| `0x08` | `stream_ready` | 1 when DMA write path is open |
| `0x0C` | `addr_ram` | IRAM/L1 base address |
| `0x10` | `addr_devmem` | Device memory base address |
| `0x14` | `addr_l2` | L2 SRAM base address |
| `0x18` | `length` | Transfer length in words |

**Test files:** All system test files exercise this module (every `write_axi_lite` and `read_axi_lite` call in `TpuRtlDriver` goes through this module).
- `tpu/verification/system/test_tpu.py` — `write_axi_lite`, `read_axi_lite`, `wait_for_flag`
- `tpu/verification/system/test_device_mem.py`
- `tpu/verification/system/test_l2_tile.py`
- `tpu/verification/system/test_tpu_compute.py`

**Test functions exercising this module:**
All test functions in the system test suite exercise AXI-Lite reads and writes. The `TpuRtlDriver` helper methods provide:
- `write_axi_lite(addr, data)` — covers write path (AWVALID+WVALID → BVALID handshake)
- `read_axi_lite(addr)` — covers read path (ARVALID → RVALID handshake)
- `wait_for_flag(offset, expected)` — polls `0x04` (`instr_ready`) and `0x08` (`stream_ready`)

**Behavioral paths covered:**
- All register write paths: offsets 0x00, 0x0C, 0x10, 0x14, 0x18 written in every test
- Register reads: offsets 0x04 (`instr_ready`) and 0x08 (`stream_ready`) polled continuously
- Doorbell set via bit 4 of offset 0x00 (P1.8 combined mode+doorbell write)
- AW and W channel handshakes complete in a single cycle (no flow control stress)

**Known coverage gaps:**
- Register readback for `addr_ram` (0x0C), `addr_devmem` (0x10), `addr_l2` (0x14), and `length` (0x18) — these are written but never read back to verify the stored values
- AXI-Lite back-pressure: `AWREADY=0` or `WREADY=0` stall conditions not exercised
- Write-after-read hazard (read in flight when a write arrives) not tested
- `BRESP` error response code never inspected

---

### `src/system/tpu_slave_axi_stream.v`

**Role:** AXI-Stream sink (DMA write path). Accepts a burst of 32-bit words from the host over the AXI-Stream slave interface, writing data to either the device memory data BRAM (`data_to_bram`) or the IRAM (`data_to_iram`) depending on `tpu_mode_stream`. Implements a three-state FSM: `IDLE → WRITE_FIFO → WRITE_BRAM`. The `data_valid` (= `fifo_wren`) combinational signal gates BRAM writes. The `write_pointer_stream` advances once per accepted handshake.

**Test files:**
- `tpu/verification/system/test_slave_stream.py` — unit tests (DUT is `tpu_slave_axi_stream` standalone)
- `tpu/verification/system/test_tpu.py` — system integration (data and IRAM write paths via `write_bram`)
- `tpu/verification/system/test_tpu_compute.py` — mode 4 IRAM writes via `write_iram`

**Test functions exercising this module:**

| Test function | Test file | Path exercised |
|---|---|---|
| `test_slave_write_n1` | `test_slave_stream.py` | IDLE→WRITE_FIFO→WRITE_BRAM, n=1 (minimum) |
| `test_slave_write_n4` | `test_slave_stream.py` | IDLE→WRITE_FIFO→WRITE_BRAM, n=4, pointer 0-3 verified |
| `test_slave_write_n8` | `test_slave_stream.py` | Bug A regression: n=8 (=FIFO depth), address 0 exactly once |
| `test_data_integrity` | `test_tpu.py` | System: n=16 data path via write_bram |
| `test_boundary_n8` | `test_tpu.py` | System: n=8, Bug A assertion |
| `test_boundary_n9` | `test_tpu.py` | System: n=9, Bug A + Bug B assertions |
| `test_boundary_n16` | `test_tpu.py` | System: n=16, Bug A + Bug B assertions |
| `test_compute_identity_kernel` | `test_tpu_compute.py` | IRAM path: mode 4, 3 instructions (6 words) |
| `test_compute_vadd_kernel` | `test_tpu_compute.py` | IRAM path: mode 4, 5 instructions (10 words) |
| `test_tma_instruction_in_kernel` | `test_tpu_compute.py` | IRAM path: mode 4, 2 instructions (4 words) |
| `test_dma_compute_overlap` | `test_tpu_compute.py` | Data path: mode 1 write concurrent with mode 3 |

**FSM states covered:**
- `IDLE` — reset state; `reset=1` holds FSM here
- `IDLE → WRITE_FIFO` transition — triggered by `S_AXIS_TVALID && write_en`; Bug A fix (`reset<=1'b0` NBA override) exercised
- `WRITE_FIFO` — `fifo_wren` fires, `write_pointer_stream` advances; data path: `data_to_bram = S_AXIS_TDATA[31:0]`
- `WRITE_BRAM` — BRAM write enable (`wea`) asserted
- IRAM path: `tpu_mode_stream=4`, `data_to_iram = S_AXIS_TDATA[63:0]` (64-bit word assembly)

**Known coverage gaps:**
- `S_AXIS_TREADY=0` back-pressure from slave to sender — slave always asserts TREADY in covered tests; stall path not tested
- IRAM path with `tlast` asserted before `len` words consumed — early termination not tested
- Simultaneous `S_AXIS_TVALID` de-assertion mid-burst (valid gap) — all tests drive continuous valid
- Mode 4 IRAM write across addresses > 8 (multi-page IRAM programs > 16 instructions not tested)

---

### `src/system/tpu_master_axi_stream.v`

**Role:** AXI-Stream source (DMA read path). Reads words from device memory BRAM and streams them to the host over the AXI-Stream master interface. Implements a three-state FSM: `IDLE → INIT_COUNTER → SEND_STREAM`. Uses an internal 8-entry FIFO (`fifo4`) to pre-fill words during `INIT_COUNTER` before asserting `M_AXIS_TVALID`. Asserts `M_AXIS_TLAST` on the final word. `M_AXIS_TDATA` is registered one cycle after `fifo_rd_en`.

**Test files:**
- `tpu/verification/system/test_master_stream.py` — unit tests (DUT is `tpu_master_axi_stream` standalone)
- `tpu/verification/system/test_tpu.py` — system integration via `read_bram`

**Test functions exercising this module:**

| Test function | Test file | Path exercised |
|---|---|---|
| `test_master_read_n1` | `test_master_stream.py` | IDLE→INIT_COUNTER→SEND_STREAM, n=1 (minimum) |
| `test_master_read_n4` | `test_master_stream.py` | n=4 (N < FIFO depth), data correctness |
| `test_master_read_n8` | `test_master_stream.py` | n=8 (N = FIFO depth), full prefill |
| `test_data_integrity` | `test_tpu.py` | System: n=16, data correctness via read_bram |
| `test_boundary_n8` | `test_tpu.py` | System: n=8 drain boundary, Bug B assertion |
| `test_boundary_n9` | `test_tpu.py` | System: n=9 prefill-to-steady-state, Bug B assertion |
| `test_boundary_n16` | `test_tpu.py` | System: n=16, Bug B assertion |
| `test_devmem_multiple_sizes` | `test_device_mem.py` | System: n=16, 64, 256 |

**FSM states covered:**
- `IDLE` — `reset=1`; enters `INIT_COUNTER` on `read_en` pulse
- `INIT_COUNTER` — runs C_M_START_COUNT-1 = 31 cycles; `init_fill_valid` prefills FIFO for count 1..min(8,N); `read_pointer_stream` advances during prefill
- `SEND_STREAM` — `axis_tvalid = !fifo_empty`; `M_AXIS_TVALID = valid_d1` (1-cycle delay); `M_AXIS_TLAST` on final word; `tx_done` when `read_pointer_stream >= N && fifo_empty`
- FIFO prefill boundary: count <= 8 (not < 8) workaround for the IDLE→INIT_COUNTER reset NBA timing
- `tlast` generation verified implicitly in all system tests

**Known coverage gaps:**
- `M_AXIS_TREADY=0` back-pressure (downstream stall) — all tests set `m00_axis_tready=1` permanently; FIFO full under back-pressure not tested
- `N > FIFO depth * 4` stress — largest tested N is 256; very large transfers not tested
- `done` signal timing relative to last `M_AXIS_TVALID` not explicitly asserted

---

### `src/system/fifo4.sv`

**Role:** 8-entry parametric FIFO used internally by `tpu_master_axi_stream` to buffer device memory words during the `INIT_COUNTER` prefill and `SEND_STREAM` phases. Exposes `empty`, `full`, and `one_item_remaining` status flags. `rd_data` is registered (1-cycle read latency).

**Test files:**
- `tpu/verification/compute_tile/test_fifo4.py` — 7 dedicated unit tests (DUT is `fifo4` standalone)
- `tpu/verification/system/test_master_stream.py` — exercised indirectly via `tpu_master_axi_stream`

**Test functions exercising this module:**

| Test function | Test file | Behavior covered |
|---|---|---|
| `test_fifo_reset` | `test_fifo4.py` | Reset → `empty=1`, `full=0` |
| `test_fifo_single_write_read` | `test_fifo4.py` | 1-cycle write + 1-cycle read latency, data integrity |
| `test_fifo_fill_and_drain` | `test_fifo4.py` | Fill to depth=8 (`full=1`), drain in order, `empty=1` after |
| `test_fifo_full_flag` | `test_fifo4.py` | `full` asserts after 8 writes, clears after read |
| `test_fifo_underflow_protection` | `test_fifo4.py` | `rd_en` on empty FIFO does not corrupt state |
| `test_fifo_one_item_remaining` | `test_fifo4.py` | `one_item_remaining` with count=1, clears at count=2 |
| `test_fifo_sequential_ops` | `test_fifo4.py` | 4-write + 4-read interleaved, data order |
| `test_master_read_n1/n4/n8` | `test_master_stream.py` | Integrated: FIFO write during prefill, drain during SEND |

**Behavioral paths covered:**
- Empty condition (`rd_data` returns undefined when empty — underflow guard holds `empty=1`)
- Full condition (overflow guard holds `full=1`; new writes while full are discarded per design)
- `one_item_remaining` flag used by `tpu_master_axi_stream` to avoid under-sending tlast
- Parametric `DEPTH` — only depth=8 is tested (compile-time parameter)

**Known coverage gaps:**
- Simultaneous `wr_en` + `rd_en` (concurrent write and read) — not explicitly tested; FIFO must handle pass-through
- `DEPTH != 8` parametrization — only default depth exercised; no test changes `DEPTH`
- Overflow: `wr_en` while `full=1` — data loss behavior not asserted

---

### `src/system/device_mem.sv`

**Role:** Device memory BRAM (65536 × 32-bit words, `blk_mem_gen_2`). Serves as the primary host-visible data buffer. Port A is used by `dma_engine` for host DMA reads and writes (modes 1 and 2). Port B is used by the `tma_engine` inside `l2_tile` for DevMem↔L2 block copies (modes 5 and 6).

**Test files:**
- `tpu/verification/system/test_device_mem.py` — dedicated device memory unit tests
- `tpu/verification/system/test_tpu.py` — indirect: every `write_bram` and `read_bram` touches device memory
- `tpu/verification/system/test_l2_tile.py` — indirect: DevMem↔L2 copies use Port B
- `tpu/verification/system/test_tpu_compute.py` — indirect: full compute flow staging through DevMem

**Test functions exercising this module:**

| Test function | Test file | Port / Path exercised |
|---|---|---|
| `test_devmem_write_read_integrity` | `test_device_mem.py` | Port A: write pattern (n=16), read back |
| `test_devmem_multiple_sizes` | `test_device_mem.py` | Port A: sizes 16, 64, 256 |
| `test_devmem_base_addr_offset` | `test_device_mem.py` | Port A: base address 0x100, 16 values |
| `test_dm_l2_roundtrip` | `test_l2_tile.py` | Port A write (mode 1), Port B read (mode 5), Port B write (mode 6) |
| `test_dm_l2_l1_l2_dm_roundtrip` | `test_l2_tile.py` | Port A + Port B (both directions) |
| `test_l2_l1_sizes` | `test_l2_tile.py` | Port A + Port B at sizes 16, 64, 128 |
| `test_l2_l1_base_addr_offset` | `test_l2_tile.py` | Port A at offsets 0x000, 0x100; Port B |
| `test_compute_identity_kernel` | `test_tpu_compute.py` | Port A at addrs 0, 8; Port B at 0, 8 |
| `test_dma_compute_overlap` | `test_tpu_compute.py` | Port A write concurrent with compute (addr 300) |

**Behavioral paths covered:**
- Port A write (`wea=1`): addresses 0, 8, 16, 32, 0x100, 0x200, 0x300
- Port A read (`ena=1, wea=0`): same address set, 1-cycle latency verified
- Port B (via tma_engine): DevMem→L2 reads, L2→DevMem writes
- 1-cycle registered read latency modeled correctly in both unit and system tests

**Known coverage gaps:**
- Port A and Port B simultaneous access to the same address — Port A/B conflict behavior (undefined for true-dual-port BRAM) not tested
- Large contiguous address ranges (addresses > 0x300 not extensively tested in unit tests; only `test_dma_compute_overlap` writes to addr 300+)
- Power-on default values (all zeros) not verified explicitly

---

### `src/l2_tile/l2_tile.sv`

**Role:** L2 shared SRAM tile (32768 × 32-bit words, `blk_mem_gen_3`). Contains the `tma_engine` sub-module which handles host-controlled DevMem↔L2 block copies (modes 5/6) and TMA-instruction-triggered copies. Port A is used by `l2_ctrl` for L2↔L1 transfers. Port B is used by `tma_engine` for DevMem access. Exposes separate done signals: `xfer_done` for host-initiated transfers, `tma_done` for instruction-triggered transfers.

**Test files:**
- `tpu/verification/system/test_l2_tile.py` — four dedicated system tests
- `tpu/verification/system/test_tpu_compute.py` — `test_tma_instruction_in_kernel` tests L2 as TMA destination

**Test functions exercising this module:**

| Test function | Test file | Modes / paths exercised |
|---|---|---|
| `test_dm_l2_roundtrip` | `test_l2_tile.py` | mode 5 (DM→L2) + mode 6 (L2→DM) at addr 0, size 32 |
| `test_dm_l2_l1_l2_dm_roundtrip` | `test_l2_tile.py` | mode 5 (addr 0x200) + mode 7 (L2 Port A) + mode 8 + mode 6 (addr 0x400) |
| `test_l2_l1_sizes` | `test_l2_tile.py` | mode 5/6/7/8 at sizes 16, 64, 128; L2 addrs 0 and 0x1000 |
| `test_l2_l1_base_addr_offset` | `test_l2_tile.py` | mode 5/7/8/6; L2 addrs 0x000, 0x100, 0x200 |
| `test_tma_instruction_in_kernel` | `test_tpu_compute.py` | TMA instruction DM→L2 (inside kernel execution) |

**Behavioral paths covered:**
- `start_dm_to_l2` pulse → `tma_engine` DM2L2_READ state
- `start_l2_to_dm` pulse → `tma_engine` L22DM state
- Port A (compute-tile side, `ct_*` ports): `l2_ctrl` drives during modes 7/8
- Port B (device-memory side, `dm_*` ports): `tma_engine` drives during modes 5/6
- `xfer_done` signal verified (implicitly through `wait_for_flag(0x04, 1)`)
- `tma_done` signal verified via `test_tma_instruction_in_kernel`

**Known coverage gaps:**
- L2 SRAM address wrapping (writes near the 32768-word boundary) not tested
- Simultaneous Port A and Port B access to overlapping L2 addresses not tested
- Board-level L2 tile coverage: no board smoke test for L2

---

### `src/l2_tile/tma_engine.sv`

**Role:** TMA (Tensor Memory Access) engine inside `l2_tile.sv`. Handles two initiation paths: host-controlled (via `start_dm_to_l2` / `start_l2_to_dm` signals) and instruction-triggered (via `tma_req` with decoded address/length fields). Manages the device memory address bus (`dm_addr`, `dm_en`, `dm_we`, `dm_din`, `dm_dout`) and the L2 SRAM Port B bus. Asserts `xfer_done` for host transfers and `tma_done` for instruction transfers.

**Test files:**
- `tpu/verification/l2_tile/test_tma.py` — 5 dedicated unit tests (DUT is `l2_tile.sv` containing `tma_engine`)
- `tpu/verification/system/test_l2_tile.py` — host-controlled paths exercised as part of system modes 5/6
- `tpu/verification/system/test_tpu_compute.py` — instruction-triggered path via `test_tma_instruction_in_kernel`

**Test functions exercising this module:**

| Test function | Test file | Transfer path exercised |
|---|---|---|
| `test_host_dm_to_l2` | `test_tma.py` | Host-controlled DM→L2 (start_dm_to_l2), n=8 |
| `test_host_l2_to_dm` | `test_tma.py` | Host-controlled L2→DM (start_l2_to_dm), n=8, non-zero base addresses |
| `test_tma_dm_to_l2` | `test_tma.py` | TMA instruction DM→L2 (tma_req, dir=0), n=8, dm_base=200, l2_base=10 |
| `test_tma_l2_to_dm` | `test_tma.py` | TMA instruction L2→DM (tma_req, dir=1), n=8, dm_base=300, l2_base=20 |
| `test_done_signal_isolation` | `test_tma.py` | `xfer_done` fires for host, `tma_done` fires for TMA; mutual exclusion verified |
| `test_dm_l2_roundtrip` | `test_l2_tile.py` | Host-controlled DM→L2 + L2→DM, n=32 |
| `test_dm_l2_l1_l2_dm_roundtrip` | `test_l2_tile.py` | Host DM→L2 at l2_addr=0x200 |
| `test_l2_l1_sizes` | `test_l2_tile.py` | DM→L2 at sizes 16, 64, 128 |
| `test_l2_l1_base_addr_offset` | `test_l2_tile.py` | DM→L2 at addr offsets 0x000, 0x100 |
| `test_tma_instruction_in_kernel` | `test_tpu_compute.py` | TMA instruction DM→L2 from inside executing kernel |

**Behavioral paths covered:**
- DM2L2 read path: `dm_addr` issue, FallingEdge `dm_dout` drive, L2 BRAM write at posedge N+1
- L22DM write path: L2 read → `dm_din` / `dm_we` assertion
- `tma_done` vs `xfer_done` isolation: host and instruction paths emit distinct done signals
- Both transfer directions (DM→L2 and L2→DM) in both host-controlled and instruction-triggered modes
- Various transfer lengths (n=4, 8, 16, 32, 64, 128)
- Non-zero base addresses (dm_base=100, 200, 300; l2_base=10, 20, 50, 100)

**Known coverage gaps:**
- TMA instruction L2→DM direction not exercised from within a kernel (`test_tma_instruction_in_kernel` only tests DM→L2)
- Simultaneous host-controlled and TMA-instruction-triggered transfers (priority arbitration path inside `tma_engine`)
- Transfer length of 1 (minimum) not unit tested

---

### `src/compute_tile/compute_tile.sv`

**Role:** Top of the compute tile. Glues all compute sub-modules: `tensorcore`, `decoder`, `l1`, `mxu`, `systolic`, `vpu_simd`, `vpu_op`, `vec_regfile`, `pc`. Exposes: start/done handshake to `compute_ctrl`; IRAM write port to `dma_engine`; L1 Port A (DMA port) to `l2_ctrl`; TMA port to `tma_engine`. Applies FP32 clamp ([1e-20, 1e20]) on MXU systolic outputs.

**Test files:**
- `tpu/verification/compute_tile/test_tensorcore.py` — exercises start/done at the compute_tile level
- `tpu/verification/compute_tile/test_mxu.py` — exercises MXU dispatch path
- `tpu/verification/compute_tile/test_vpu_simd.py` — exercises VPU dispatch path
- `tpu/verification/system/test_tpu_compute.py` — system-level: all four compute tests exercise compute_tile via compute_ctrl

**Test functions exercising this module:**

| Test function | Test file | Capability exercised |
|---|---|---|
| `test_tensorcore_halt` | `test_tensorcore.py` | start pulse → HALT → done pulse |
| `test_tensorcore_vload_vhalt` | `test_tensorcore.py` | IRAM write, VLOAD dispatch, done |
| `test_tensorcore_vpu_data_flow` | `test_tensorcore.py` | IRAM write, VLOAD→VSTORE identity, L1 Port B |
| `test_compute_identity_kernel` | `test_tpu_compute.py` | System: IRAM write (Port A), start, VLOAD+VSTORE, done, L1 Port A |
| `test_compute_vadd_kernel` | `test_tpu_compute.py` | System: VLOAD×2, VCOMPUTE, VSTORE |
| `test_tma_instruction_in_kernel` | `test_tpu_compute.py` | System: TMA instruction dispatch |
| `test_dma_compute_overlap` | `test_tpu_compute.py` | System: concurrent with dma_engine |

**Behavioral paths covered:**
- IRAM write via `dma_iram_din` / `instr_write_en` (Port A, DMA engine)
- `start` pulse → `tensorcore` begins fetch cycle
- `done` pulse from `tensorcore` back to `compute_ctrl`
- L1 Port A (DMA): `l2_ctrl` reads and writes L1 BRAM during modes 7/8
- L1 Port B (compute): `tensorcore` / `vpu_simd` / `mxu` drive L1 during kernel execution
- FP32 clamp: active on MXU output path (implicit in any MXU result test)

**Known coverage gaps:**
- MXU dispatch from system level (no system test runs an MXU matmul kernel end-to-end)
- Simultaneous L1 Port A (l2_ctrl DMA) and Port B (tensorcore) access — port arbitration not tested
- TMA port from kernel to `tma_engine` — only DM→L2 direction tested in system

---

### `src/compute_tile/tensorcore.sv`

**Role:** Instruction fetch and dispatch FSM. Fetches 64-bit instructions from IRAM (`blk_mem_gen_1`) using the program counter (`pc`), decodes via `decoder.sv`, and dispatches to MXU, VPU, or TMA engines. FSM states: `FETCH` (wait for IRAM read latency), `IDLE` (decode and dispatch), `MXU_EXEC`, `MXU_WAIT`, `VPU_EXEC`, `VPU_WAIT`, `TMA_EXEC`, `TMA_WAIT`, `HALT`.

**Test files:**
- `tpu/verification/compute_tile/test_tensorcore.py` — 3 unit tests
- `tpu/verification/system/test_tpu_compute.py` — all 4 system compute tests exercise tensorcore

**Test functions exercising this module:**

| Test function | Test file | States visited |
|---|---|---|
| `test_tensorcore_halt` | `test_tensorcore.py` | FETCH → IDLE → HALT |
| `test_tensorcore_vload_vhalt` | `test_tensorcore.py` | FETCH → IDLE → VPU_EXEC → VPU_WAIT → FETCH → IDLE → HALT |
| `test_tensorcore_vpu_data_flow` | `test_tensorcore.py` | FETCH → IDLE → VPU_EXEC → VPU_WAIT (×2) → HALT |
| `test_compute_identity_kernel` | `test_tpu_compute.py` | VPU_EXEC/WAIT → VPU_EXEC/WAIT → HALT |
| `test_compute_vadd_kernel` | `test_tpu_compute.py` | VPU_EXEC/WAIT (×4) → HALT |
| `test_tma_instruction_in_kernel` | `test_tpu_compute.py` | TMA_EXEC → TMA_WAIT → HALT |
| `test_dma_compute_overlap` | `test_tpu_compute.py` | VPU_EXEC/WAIT (×2) → HALT |

**FSM states covered:**
- `FETCH` — IRAM read issued, 1-cycle latency wait
- `IDLE` — instruction decoded, dispatch decision made
- `VPU_EXEC` — `vpu_start` asserted; entered for VLOAD, VSTORE, VCOMPUTE instructions
- `VPU_WAIT` — wait for `vpu_done`
- `TMA_EXEC` — `tma_req` asserted; entered for TMA instruction (MODE=2)
- `TMA_WAIT` — wait for `tma_done`
- `HALT` — execution complete; `done=1`

**Known coverage gaps:**
- `MXU_EXEC` / `MXU_WAIT` states — no system-level test dispatches an MXU (MODE=1) instruction end-to-end; only unit-level `test_mxu.py` exercises the MXU controller in isolation
- Multi-instruction programs longer than 5 instructions (largest in system tests is 5 instructions in `test_compute_vadd_kernel`)
- PC wrap-around: programs that exceed IRAM[255] not tested
- IRAM word-pair assembly (64-bit instruction from two 32-bit stream words) exercised in all compute tests but never verified by direct IRAM readback

---

### `src/compute_tile/decoder.sv`

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

---

### `src/compute_tile/l1.sv`

**Role:** L1 data BRAM (8192 × 32-bit words, `blk_mem_gen_0`) with address mux. Dual-port: Port A is the DMA port (driven by `l2_ctrl` for L2↔L1 transfers); Port B is the compute port (driven by `vpu_simd` for VLOAD/VSTORE and by `mxu` for matrix reads/writes). The address mux selects between the DMA pointer and the compute pointer on Port A.

**Test files:**
- `tpu/verification/compute_tile/test_mxu.py` — Port B (compute): MXU matrix reads
- `tpu/verification/compute_tile/test_vpu_simd.py` — Port B (compute): VLOAD/VSTORE data paths
- `tpu/verification/compute_tile/test_tensorcore.py` — Port B via `test_tensorcore_vpu_data_flow`
- `tpu/verification/system/test_l2_tile.py` — Port A (DMA): `l2_ctrl` writes and reads via modes 7/8
- `tpu/verification/system/test_tpu_compute.py` — Port A (DMA) + Port B (compute) in full flow

**Behavioral paths covered:**
- Port A write (`l1_dma_wr_en`): `l2_ctrl` writes L2 data to L1 during mode 7
- Port A read (`l1_dma_rd_en`): `l2_ctrl` reads L1 data to L2 during mode 8
- Port B write (`bram_we_b`): `vpu_simd` VSTORE writes vector register to L1
- Port B read (`bram_en_b`, `bram_we_b=0`): `vpu_simd` VLOAD reads L1 into vector register; `mxu` reads weight and activation matrices
- 1-cycle registered read latency modeled correctly in all test drivers

**Known coverage gaps:**
- Simultaneous Port A and Port B access to the same address — true-dual-port behavior (read-first vs write-first) not tested
- L1 addresses near the 8192-word boundary not tested

---

### `src/compute_tile/mxu.sv`

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

---

### `src/compute_tile/systolic.sv` + `pe.sv`

**Role:** `systolic.sv` instantiates an N×N array of processing elements (`pe.sv`). Each PE implements a multiply-accumulate (MAC) in weight-stationary mode: the weight is held, activations flow horizontally, and partial sums flow vertically. `pe.sv` produces `pe_out = activation_in * weight + sum_in` using `fp32_mul` + `fp32_add`.

**Test files:**
- `tpu/verification/compute_tile/test_systolic_array.py` — 1 randomized suite test
- `tpu/verification/compute_tile/test_pe.py` — 4 unit tests for a single PE
- `tpu/verification/compute_tile/test_mxu.py` — exercised indirectly via MXU controller

**Test functions exercising this module:**

| Test function | Test file | Coverage |
|---|---|---|
| `test_systolic_array_4x4_random_suite` | `test_systolic_array.py` | 100 random 4×4 matmuls; output verified bit-exact to NumPy FP32 |
| `test_pe` | `test_pe.py` | Basic MAC: `out = a*w + sum` |
| `test_pe_fp32_extremes_and_signs` | `test_pe.py` | Very large/small values, sign combinations |
| `test_pe_back_to_back_valid` | `test_pe.py` | Valid high for multiple consecutive cycles |
| `test_pe_enable_disable` | `test_pe.py` | PE enable/disable; output freezes when disabled |

**Behavioral paths covered:**
- Weight stationary: weight loaded once, activations stream through
- MAC accumulation: multiple partial sums accumulated correctly
- Array flush: all PEs drain after last activation
- 100 random test cases verify numerical correctness

**Known coverage gaps:**
- N != 4 systolic array sizes — only 4×4 is tested
- Systolic array with partial zero activations (sparse input)
- Overflow and underflow through the full N×N sum path

---

### `src/compute_tile/vpu_simd.sv`

**Role:** SIMD vector processing unit. Implements VLOAD (read 8 FP32 words from L1 into a vector register), VSTORE (write vector register to L1), VCOMPUTE (arithmetic on two vector registers), and SCALAR (broadcast scalar from L1 to one operand). FSM states: `IDLE`, VLOAD states (`VLOAD_REQ`, `VLOAD_WAIT`, `VLOAD_LATCH`), VSTORE states (`VSTORE_REQ`, `VSTORE_WRITE`), `VCOMPUTE`, `SCALAR_READ_A`, `SCALAR_WAIT_A`, `SCALAR_LATCH_A`, `SCALAR_WAIT_B`, `SCALAR_COMPUTE`, `DONE_STATE`.

**Test files:**
- `tpu/verification/compute_tile/test_vpu_simd.py` — 10 dedicated unit tests

**Test functions exercising this module:**

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

**FSM states covered:**
- `IDLE` — reset state, start signal transitions to active state
- VLOAD path: `VLOAD_REQ` (BRAM address issued), `VLOAD_WAIT` (1-cycle BRAM latency), `VLOAD_LATCH` (data captured into vector register)
- VSTORE path: `VSTORE_REQ` (vector register data driven), `VSTORE_WRITE` (BRAM wea asserted)
- `VCOMPUTE` — `vpu_op` sub-module computes result per lane
- SCALAR path: `SCALAR_READ_A` (issue L1 read for scalar), `SCALAR_WAIT_A` (BRAM latency), `SCALAR_LATCH_A` (latch scalar), `SCALAR_WAIT_B` (second BRAM read if needed), `SCALAR_COMPUTE` (broadcast and compute)
- `DONE_STATE` — done pulse, return to IDLE

**Known coverage gaps:**
- `test_vcompute_scalar_broadcast`: timing only verified, not data values of scalar broadcast result
- VMUL (`vpu_opcode=1`) and D_RELU (`vpu_opcode=4`) not exercised in system-level kernel
- VCOMPUTE with MAX opcode (`vpu_opcode=3`) not tested in `test_vpu_simd.py`
- Multi-register programs (accumulating into vreg 3–7) not tested; only vreg 0, 1, 2 used

---

### `src/compute_tile/vpu_op.sv`

**Role:** Per-lane vector operation module. Takes two 8×FP32 operand vectors and an opcode, and computes the result for all 8 lanes combinationally. Opcodes: 0=VADD, 1=VMUL, 2=RELU (max(0,x)), 3=MAX (element-wise max), 4=D_RELU (derivative: 1 if x>0, else 0).

**Test files:**
- `tpu/verification/compute_tile/test_vpu_op.py` — 7 dedicated unit tests

**Test functions exercising this module:**

| Test function | Opcode | Coverage |
|---|---|---|
| `test_vpu_add_basic` | 0 (VADD) | Known FP32 values, bit-exact |
| `test_vpu_sub_basic` | (opcode for sub) | Subtraction correctness |
| `test_vpu_relu` | 2 (RELU) | Positive, negative, zero inputs |
| `test_vpu_mul_basic` | 1 (VMUL) | Multiplication correctness |
| `test_vpu_relu_derivative` | 4 (D_RELU) | Positive → 1.0, non-positive → 0.0 |
| `test_vpu_randomized` | 0, 1, 2 | 100 random cases across add/mul/relu |
| `test_vpu_stress_fp32_edges` | 0 | Denormals, infinities, NaN edge cases |

**Behavioral paths covered:**
- All 5 opcode paths (0–4) verified at unit level
- FP32 edge cases (denormals, signed zero, large magnitude) exercised

**Known coverage gaps:**
- opcode=3 (MAX) not covered in `test_vpu_randomized` (only opcodes 0, 1, 2 in randomized suite)
- D_RELU (opcode=4) not exercised from `vpu_simd` or system level

---

### `src/compute_tile/vec_regfile.sv`

**Role:** Vector register file with 8 registers of 8 FP32 lanes each. Dual-port: write port (synchronous, write-enable gated) and two independent read ports. Used by `vpu_simd` to hold intermediate vectors between VLOAD, VCOMPUTE, and VSTORE instructions.

**Test files:**
- `tpu/verification/compute_tile/test_vec_regfile.py` — 5 dedicated unit tests

**Test functions exercising this module:**

| Test function | Coverage |
|---|---|
| `test_regfile_reset` | After reset, all registers read as zero |
| `test_regfile_write_read` | Write to each register, read back; all 8 registers |
| `test_regfile_dual_port` | Two simultaneous reads from different registers |
| `test_regfile_all_registers` | Sequential write + read across all 8 register addresses |
| `test_regfile_write_disabled` | Write enable = 0; register value unchanged |

**Behavioral paths covered:**
- All 8 register addresses (0–7) written and read
- Dual read port simultaneous access
- Write enable gating

**Known coverage gaps:**
- Simultaneous write and read to the same register address (read-during-write behavior)
- FP32 lane isolation: only the first lane is verified in most tests; 8-lane vectors not all asserted

---

### `src/compute_tile/fp32_add.sv` + `fp32_mul.sv`

**Role:** IEEE-754 single-precision FP32 adder and multiplier. Purely combinational blocks used by `pe.sv` (MAC) and `vpu_op.sv` (per-lane operations).

**Test files:**
- `tpu/verification/compute_tile/test_fp32_add.py` — 1 test function (vector of cases)
- `tpu/verification/compute_tile/test_fp32_mul.py` — 1 test function (vector of cases)
- Exercised indirectly by: `test_pe.py`, `test_vpu_op.py`, `test_vpu_simd.py`, `test_systolic_array.py`

**Test functions exercising this module:**

| Test function | Test file | Coverage |
|---|---|---|
| `test_fp32_add_vectors` | `test_fp32_add.py` | Vector of known FP32 pairs; result bit-exact vs Python |
| `test_fp32_mul_vectors` | `test_fp32_mul.py` | Vector of known FP32 pairs; result bit-exact vs Python |

**Behavioral paths covered:**
- Normal FP32 addition and multiplication across a range of magnitudes and signs
- Bit-exact comparison to Python `struct.pack` reference

**Known coverage gaps:**
- Subnormal (denormal) inputs not isolated in unit tests (covered partially in `test_vpu_stress_fp32_edges`)
- Overflow (result exceeds FP32 max) not tested at `fp32_add` / `fp32_mul` unit level
- NaN and infinity propagation not tested at unit level

---

### `src/compute_tile/pc.sv`

**Role:** Program counter. Supports reset, increment, conditional hold, and load (jump) operations. Used by `tensorcore.sv` to sequence through IRAM instructions.

**Test files:**
- `tpu/verification/compute_tile/test_pc.py` — 6 dedicated unit tests

**Test functions exercising this module:**

| Test function | Coverage |
|---|---|
| `test_pc_reset` | PC = 0 after reset |
| `test_pc_increment` | PC increments by 1 on each enable cycle |
| `test_pc_load` | PC jumps to loaded value when load signal asserted |
| `test_pc_hold` | PC holds current value when hold signal asserted |
| `test_pc_load_priority` | Load takes priority over increment |
| `test_pc_wrap_around` | PC wraps from max (255) to 0 |

**Behavioral paths covered:**
- All four operational modes: reset, increment, hold, load
- Load priority over increment
- 8-bit wrap-around at address 255

**Known coverage gaps:**
- `hold` and `load` simultaneously asserted (priority undefined)
- PC used inside a multi-instruction kernel is exercised implicitly in system tests but the PC value is not directly observable from the system test bench

---

## Summary Table: Tests to Modules

| Test File | Modules Under Test (Primary) | Modules Exercised (Secondary) |
|---|---|---|
| `verification/system/test_tpu.py` | `tpu.sv`, `tpu_slave_axi_lite.v`, `tpu_slave_axi_stream.v`, `tpu_master_axi_stream.v` | `device_mem.sv`, `fifo4.sv` |
| `verification/system/test_data_integrity.py` | `tpu.sv`, `dma_engine.sv` | `tpu_slave_axi_lite.v`, `tpu_slave_axi_stream.v`, `tpu_master_axi_stream.v`, `device_mem.sv` |
| `verification/system/test_device_mem.py` | `device_mem.sv`, `dma_engine.sv` | `tpu.sv`, `tpu_slave_axi_lite.v`, `tpu_slave_axi_stream.v`, `tpu_master_axi_stream.v` |
| `verification/system/test_l2_tile.py` | `l2_tile.sv`, `tma_engine.sv`, `l2_ctrl.sv`, `dma_engine.sv` | `tpu.sv`, `tpu_slave_axi_lite.v`, `device_mem.sv`, `l1.sv` |
| `verification/system/test_tpu_compute.py` | `tpu.sv`, `dma_engine.sv`, `compute_ctrl.sv`, `l2_ctrl.sv`, `compute_tile.sv`, `tensorcore.sv` | All system + compute_tile sub-modules |
| `verification/system/test_slave_stream.py` | `tpu_slave_axi_stream.v` | (standalone unit test) |
| `verification/system/test_master_stream.py` | `tpu_master_axi_stream.v`, `fifo4.sv` | (standalone unit test) |
| `verification/l2_tile/test_tma.py` | `tma_engine.sv`, `l2_tile.sv` | (standalone unit test) |
| `verification/compute_tile/test_tensorcore.py` | `tensorcore.sv`, `decoder.sv`, `pc.sv` | `l1.sv`, `vpu_simd.sv` |
| `verification/compute_tile/test_decoder.py` | `decoder.sv` | (standalone unit test) |
| `verification/compute_tile/test_isa_decoder.py` | `decoder.sv` | (standalone; compiler field layout) |
| `verification/compute_tile/test_mxu.py` | `mxu.sv`, `systolic.sv`, `pe.sv` | `l1.sv` (behavioral model) |
| `verification/compute_tile/test_systolic_array.py` | `systolic.sv`, `pe.sv` | `fp32_add.sv`, `fp32_mul.sv` |
| `verification/compute_tile/test_pe.py` | `pe.sv` | `fp32_add.sv`, `fp32_mul.sv` |
| `verification/compute_tile/test_vpu_simd.py` | `vpu_simd.sv`, `vec_regfile.sv`, `vpu_op.sv` | `l1.sv` (behavioral model) |
| `verification/compute_tile/test_vpu_op.py` | `vpu_op.sv` | `fp32_add.sv`, `fp32_mul.sv` |
| `verification/compute_tile/test_vec_regfile.py` | `vec_regfile.sv` | (standalone unit test) |
| `verification/compute_tile/test_fifo4.py` | `fifo4.sv` | (standalone unit test) |
| `verification/compute_tile/test_fp32_add.py` | `fp32_add.sv` | (standalone unit test) |
| `verification/compute_tile/test_fp32_mul.py` | `fp32_mul.sv` | (standalone unit test) |
| `verification/compute_tile/test_pc.py` | `pc.sv` | (standalone unit test) |

---

## Known Issues

### Issue 1: IRAM `addr_ram=1` Workaround (Sim-Only)

**Symptom:** When loading N instructions starting at IRAM[0] via mode 4 (WRITE_IRAM) using the AXI-Stream path, setting `addr_ram=0` causes instructions 1 through N-1 to be written at incorrect IRAM addresses — specifically, each instruction is written to the address one lower than intended.

**Root cause:** In `tpu.sv`, the `iram_addr` counter and `blk_mem_gen_1` write enable (`wea`) both fire at the same `posedge clk`. The BRAM behavioral model (`blk_mem_models.sv`) captures `addra` using the pre-NBA (pre-non-blocking-assignment) value of `iram_addr` — the value that was stable before the current clock edge's assignments resolved. On the first odd `write_pointer_stream` cycle (which triggers the first BRAM write), the pre-NBA `iram_addr` is the value from the previous cycle, not the value being assigned in this cycle.

**Detailed trace with `addr_ram=0`:**
```
write_pointer=1: BRAM write at pre-NBA addr=0   → instr 0 at IRAM[0]  (correct)
write_pointer=3: BRAM write at pre-NBA addr=0   → instr 1 at IRAM[0]  (WRONG: overwrites instr 0)
write_pointer=5: BRAM write at pre-NBA addr=1   → instr 2 at IRAM[1]  (should be IRAM[2])
write_pointer=7: BRAM write at pre-NBA addr=2   → instr 3 at IRAM[2]  (should be IRAM[3])
```

**Workaround:** Set `addr_ram=1` (not 0) when loading N instructions starting at IRAM[0]. With `addr_ram=1`, the pre-NBA address sequence produces the correct 0-based addresses:
```
addr_ram=1:
  write_pointer=1: pre-NBA iram_addr = 1+0 = 0  → instr 0 at IRAM[0]  (correct)
  write_pointer=3: pre-NBA iram_addr = 1+0 = 1  → instr 1 at IRAM[1]  (correct)
  write_pointer=5: pre-NBA iram_addr = 1+1 = 2  → instr 2 at IRAM[2]  (correct)
  write_pointer=7: pre-NBA iram_addr = 1+2 = 3  → instr 3 at IRAM[3]  (correct)
```

**Application in tests:** `test_tpu_compute.py` applies this workaround in `TpuComputeDriver.write_iram()` at line 52: `await self.write_axi_lite(0x0C, 1)`. The module docstring (lines 6–14, referenced at line 14) documents the full analysis.

**Status:** Sim-only timing artifact of the cocotb VPI write coinciding with the BRAM posedge sampling. In synthesis, the BRAM IP captures the address combinationally before posedge (registered output mode). Tracked as P3 (low priority) — fix: update `iram_addr` one cycle before the BRAM write enable, or use a registered write enable.

---

### Issue 2: Bug A — `tpu_slave_axi_stream` IDLE→WRITE_FIFO Reset Stall (Historically Fixed 2026-02-25)

**Symptom:** On the `IDLE→WRITE_FIFO` transition, the `reset` register stayed HIGH for one extra cycle due to a structural NBA ordering issue, causing `write_pointer_stream` to remain at 0 for two cycles. The second incoming word overwrote BRAM address 0, losing the first word.

**Root cause:** The AXI-Stream FSM has a structural anti-pattern where the `else` branch (which should clear `reset`) lacks `begin`/`end`:
```verilog
if (!ARESETN) begin
  state <= IDLE;
end
else            // ← no begin/end
  reset <= 1'b0;
case (state)
  IDLE: begin
    reset <= 1'b1;  // ← NBA in IDLE case overrides the else-reset
    if (start) ...
  end
endcase
```
On the IDLE→WRITE_FIFO transition, the IDLE case still assigns `reset <= 1'b1` as an NBA. Block 1 (which checks `if (!ARESETN || reset)`) fires the reset branch on the first cycle of WRITE_FIFO.

**Fix:** Explicit `reset <= 1'b0` inside the IDLE→WRITE_FIFO transition branch (last NBA wins). Applied in `tpu_slave_axi_stream.v` line 123.

**Regression test:** `test_slave_write_n8` in `test_slave_stream.py` asserts that address 0 is written exactly once. `test_boundary_n8`, `test_boundary_n9`, `test_boundary_n16` in `test_tpu.py` assert that the first element equals 0.0 (Bug A assertion).

**Status:** FIXED. All regression tests pass as of 2026-02-25.

---

### Issue 3: Bug B — `tpu_master_axi_stream` Last FIFO Word Duplicate Reanalysis (2026-02-27)

**Symptom (initially reported):** The last word in a FIFO drain sequence was suspected to be duplicated at the N=8 boundary — specifically, `valid_d1` (the one-cycle delayed version of `axis_tvalid`) might cause `rd_data` to be sampled twice for the last FIFO word.

**Reanalysis conclusion (2026-02-27):** Bug B does NOT exist. `valid_d1` and `rd_data` are inherently aligned because `rd_data` is registered from `fifo_rd_data` at the same posedge that `valid_d1` captures `axis_tvalid`. The timing is:
```
Cycle N:   fifo_rd_en=1     → fifo_rd_data latched at posedge N+1
Cycle N:   axis_tvalid=1    → valid_d1 latched at posedge N+1
Cycle N+1: M_AXIS_TDATA = rd_data (latched from fifo_rd_data)
Cycle N+1: M_AXIS_TVALID = valid_d1
```
Both signals advance in lockstep. The final BRAM word is not duplicated.

**Test evidence:** `test_boundary_n8`, `test_boundary_n9`, `test_boundary_n16` in `test_tpu.py` all assert `result[i] != result[i+1]` (no adjacent duplicates). These tests pass cleanly in simulation.

**Status:** NOT A BUG (reanalysis complete). The original concern was a false positive from an earlier analysis of a different timing diagram.

---

### Issue 4: Board +2 Word Shift in DMA Reads (Open)

**Symptom:** In board smoke tests (`demos/programs/smoke_board.tu`), DMA reads return data with a +2 word offset compared to what was written. The correct pattern is shifted by exactly 2 words.

**Root cause (suspected):** The Vivado block RAM IP (`blk_mem_gen_0`) is configured with output-register mode enabled, producing 2 pipeline stages total (1-cycle address → 1-cycle output register) instead of the 1-cycle latency modeled in simulation (`blk_mem_models.sv`). The `tpu_master_axi_stream` module is compiled with `BRAM_READ_LATENCY = 1` and `count <= 8` (not `< 8`) in the `INIT_COUNTER` prefill window. With 2-cycle synthesis latency, the prefill should use a window of `count <= 9` and `M_AXIS_TDATA` would arrive 1 cycle later, explaining a +2 word offset.

**Simulation status:** All 11 system simulation tests pass (1-cycle latency model is correct for sim).

**Resolution:** Rebuild bitstream with BRAM IP configured for 1-cycle output latency (no output register stage), or update `BRAM_READ_LATENCY` and the `count <= 8` window to match the 2-cycle synthesis latency.

**Status:** OPEN. Tracked in `PLAN.md`. Board smoke test (`smoke_board.tu`) reproduces the shift. No bitstream rebuild yet.

---

## Concurrent Execution (P2.08)

The P2.08 refactor replaced the original monolithic `tpu.sv` FSM with a thin concurrent arbiter that dispatches to three independent sub-FSMs:

| Sub-FSM | Module | Modes | BRAM Resource Ownership |
|---|---|---|---|
| `dma_engine` | `src/system/dma_engine.sv` | 1, 2, 4, 5, 6 | `device_mem` Port A; `l2_tile` Port B (via `tma_engine`) |
| `compute_ctrl` | `src/system/compute_ctrl.sv` | 3 | `l1` Port B (via `tensorcore`); `tma_engine` Port B (TMA instr) |
| `l2_ctrl` | `src/system/l2_ctrl.sv` | 7, 8 | `l2_tile` Port A; `l1` Port A |

**Concurrent safety:** All three sub-FSMs own disjoint BRAM ports. No two sub-FSMs contend for the same BRAM port simultaneously (by hardware design and software contract). The arbiter enforces group exclusivity — within each group, only one operation runs at a time — but allows across-group concurrency.

**Port mapping:**
- `device_mem` Port A: owned by `dma_engine` (modes 1, 2)
- `device_mem` Port B: owned by `tma_engine` inside `l2_tile` (modes 5, 6; TMA instruction)
- `l2_tile` Port A (`ct_*`): owned by `l2_ctrl` (modes 7, 8)
- `l2_tile` Port B (`dm_*`): owned by `tma_engine` (modes 5, 6)
- `l1` Port A (DMA): owned by `l2_ctrl` (modes 7, 8)
- `l1` Port B (compute): owned by `tensorcore` / `vpu_simd` / `mxu` during mode 3

**`instr_ready` semantics:**
```
instr_ready = !dma_running && !compute_running && !l2_running
```
Each sub-FSM drives its `_running` flag in the arbiter. `instr_ready` goes LOW when any sub-FSM starts and returns HIGH only when all three are idle. This is backward-compatible with single-operation-at-a-time host drivers.

**`test_dma_compute_overlap` — Concurrent execution test:**

Located in `tpu/verification/system/test_tpu_compute.py`, `test_dma_compute_overlap` is the only test that explicitly exercises concurrent execution. The test sequence:

1. **Setup (sequential):** Load identity kernel into IRAM; stage input data into L1[0:7] via DevMem→L2→L1.
2. **Step A:** Fire mode 3 COMPUTE doorbell — `compute_ctrl` enters `CC_RUNNING`, `instr_ready` goes LOW. Do NOT call `wait_for_flag`.
3. **Step B:** Immediately fire mode 1 WR_DEVMEM doorbell to DevMem[300:307] — arbiter dispatches to `dma_engine` while `compute_ctrl` is running. `dma_engine` enters `DE_WRITE`.
4. **Step C:** Wait for `stream_ready`, send 8 DMA words to DevMem[300:307].
5. **Step D:** Wait for `instr_ready=1` — both sub-FSMs must complete.
6. **Verify DMA:** DevMem[300:307] == dma_data (42.0 + i).
7. **Verify compute:** L1[8:15] == original input_data (1.0..8.0).

**Test verifies:**
- The arbiter accepts a new DMA doorbell while `compute_ctrl` is running
- `dma_engine` DE_WRITE executes concurrently with `compute_ctrl` CC_RUNNING
- `stream_ready` is asserted by `dma_engine` even while `compute_ctrl` holds `compute_running=1`
- Neither result is corrupted: compute result and DMA result are independently correct
- `instr_ready` re-asserts only after both sub-FSMs are idle

**Software contract for concurrent execution:**
- Within a group, one operation at a time (e.g., do not issue mode 5 while mode 6 is running)
- Exception: mode 4 (WRITE_IRAM) shares the IRAM with mode 3 (COMPUTE) — software must not issue mode 4 while mode 3 is executing
- DMA modes (1/2/4/5/6) may run concurrently with compute (mode 3) and L2 transfers (7/8) since they use disjoint BRAM ports

---

## Coverage Gaps Summary

| Category | Covered | Missing / Partial |
|---|---|---|
| System modes (tpu.sv arbiter) | 1, 2, 3, 4, 5, 6, 7, 8 | Invalid mode (> 8); explicit mode-0 IDLE command |
| Concurrent execution | mode 3 + mode 1 overlap | mode 3 + mode 7/8 overlap; mode 1 + mode 7 overlap |
| AXI-Lite | write path (all regs); read path (0x04, 0x08) | readback of 0x0C, 0x10, 0x14, 0x18; back-pressure (AWREADY=0) |
| AXI-Stream write | n=1, 4, 8, 16, 64, 256; Bug A regression | back-pressure (TREADY=0 stall); valid gap mid-burst |
| AXI-Stream read | n=1, 4, 8, 16, 64, 256; Bug B regression | back-pressure (TREADY=0 downstream stall) |
| FIFO4 | empty, full, one_item_remaining, drain, underflow | concurrent wr_en+rd_en; DEPTH != 8; overflow data loss |
| Device memory | Port A r/w at multiple addr/sizes; Port B via TMA | Port A + Port B simultaneous same address |
| L2 tile | modes 5, 6, 7, 8; TMA instr DM→L2 | TMA instr L2→DM from kernel; L2 address wrap |
| TMA engine | both directions; host and instr triggers; done isolation | simultaneous host + instr trigger; length=1 |
| Tensorcore FSM | FETCH, IDLE, VPU_EXEC/WAIT, TMA_EXEC/WAIT, HALT | MXU_EXEC/WAIT (no system-level MXU kernel) |
| Decoder | all 4 modes; VPU sub-fields; addr fields; randomized | TMA sub-fields in isolation; opcode=3 (MAX) |
| MXU | IDLE, START, INIT_COUNTER, MATMUL_WAIT, WRITE_DONE | system-level MXU dispatch (only unit tested) |
| Systolic + PE | 100 random 4×4 cases; MAC; enable/disable | N != 4; sparse input; overflow through sum path |
| VPU SIMD | VLOAD, VSTORE, VCOMPUTE, SCALAR (add/relu/mul); reset | VCOMPUTE scalar broadcast data values; MAX opcode |
| VPU op | all 5 opcodes (0–4) | MAX (opcode=3) in randomized suite; D_RELU from system |
| Vec regfile | all 8 regs; dual read port; write-enable gating | simultaneous write+read same addr; 8-lane vector isolation |
| FP32 arithmetic | normal range; randomized; edge cases via vpu_stress | subnormal isolation; overflow; NaN propagation |
| PC | reset, increment, hold, load, wrap, priority | hold+load simultaneous; observable from system test |
| Reset mid-transfer | — | aresetn=0 during active mode — behavior undefined |
| Board | modes 1, 2 basic (DEADBEEF) | Open: +2 shift bug; no board L2/compute test |
