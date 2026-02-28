# Verification: tpu_master_axi_stream.v

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
