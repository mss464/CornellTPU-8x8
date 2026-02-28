# Verification: tpu_slave_axi_stream.v

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

## `src/system/tpu_slave_axi_lite.v`

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
