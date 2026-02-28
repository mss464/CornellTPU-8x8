# Verification: l2_tile.sv + tma_engine.sv

L2 tile and TMA engine verification. Tests cover DevMem↔L2 and L2↔L1 hierarchy transfers.

---

## src/l2_tile/l2_tile.sv

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

## src/l2_tile/tma_engine.sv

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
