# Verification: fifo4.sv

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
