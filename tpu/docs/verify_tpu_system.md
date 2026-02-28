# Verification: tpu.sv (System Top)

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

## `src/system/dma_engine.sv`

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

## `src/system/compute_ctrl.sv`

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

## `src/system/l2_ctrl.sv`

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
