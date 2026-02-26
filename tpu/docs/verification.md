# Mini-TPU Verification Coverage

> Living document — updated as tests are added or gaps are closed.
> See `PLAN.md` for the task backlog and `PROGRESS.md` for recent changes.

---

## Table 1 — Module Coverage Matrix

| Module | Unit Test | System Test | Board Test |
|---|---|---|---|
| `tpu.sv` (FSM) | — | `test_data_integrity` (modes 1/2), `test_device_mem`, `test_l2_tile` (modes 5–8) | `smoke_board` (modes 1/2) |
| `tpu_slave_axi_lite.v` | — | Exercised by all system tests | Board |
| `tpu_slave_axi_stream.v` | — | `test_data_integrity`, `test_device_mem` | Board |
| `tpu_master_axi_stream.v` | — | `test_data_integrity`, `test_device_mem` | Board |
| `device_mem.sv` | — | `test_device_mem` | Board |
| `l2_tile.sv` | — | `test_l2_tile` | **MISSING** |
| `compute_tile.sv` | — | **MISSING** (no COMPUTE mode test) | **MISSING** |
| `tensorcore.sv` | `test_tensorcore` (HALT, VLOAD+HALT, data flow) | **MISSING** | **MISSING** |
| `decoder.sv` | `test_decoder` (raw field layout), `test_isa_decoder` (compiler format) | — | — |
| `vpu_simd.sv` | `test_vpu_simd` (all ops + data correctness) | **MISSING** | **MISSING** |
| `vpu_op.sv` | `test_vpu_op` | — | — |
| `vec_regfile.sv` | `test_vec_regfile` | — | — |
| `mxu.sv` | `test_mxu` | — | — |
| `systolic.sv` | `test_systolic_array` | — | — |
| `pe.sv` | `test_pe` | — | — |
| `fp32_add.sv` | `test_fp32_add` | — | — |
| `fp32_mul.sv` | `test_fp32_mul` | — | — |
| `l1.sv` (data BRAM) | Indirect (via tensorcore/mxu/vpu_simd tests) | `test_l2_tile` (modes 7/8) | — |
| `fifo4.sv` | `test_fifo4` | — | — |
| `pc.sv` | `test_pc` | — | — |

---

## Table 2 — Hardware Behavior Coverage

| Hardware Behavior | Covered By | Status |
|---|---|---|
| Host → DevMem write (mode 1) | `test_data_integrity`, `test_device_mem` | ✓ COVERED |
| Host ← DevMem read (mode 2) | `test_data_integrity`, `test_device_mem` | ✓ COVERED |
| DevMem → L2 block copy (mode 5) | `test_l2_tile::test_dm_l2_roundtrip` | ✓ COVERED |
| L2 → DevMem block copy (mode 6) | `test_l2_tile::test_dm_l2_roundtrip` | ✓ COVERED |
| L2 → L1 block copy (mode 7) | `test_l2_tile::test_dm_l2_l1_l2_dm_roundtrip` | ✓ COVERED |
| L1 → L2 block copy (mode 8) | `test_l2_tile::test_dm_l2_l1_l2_dm_roundtrip` | ✓ COVERED |
| L2/L1 transfer sizes (16, 64, 128) | `test_l2_tile::test_l2_l1_sizes` | ✓ COVERED |
| L2/L1 base address offsets | `test_l2_tile::test_l2_l1_base_addr_offset` | ✓ COVERED |
| BRAM 1-cycle read latency | `blk_mem_models.sv` behavioral model | ✓ MODELED |
| AXI-Lite register write | All system tests (via write_axi_lite) | ✓ COVERED |
| AXI-Lite register read | `wait_for_flag` (reads 0x04, 0x08) | PARTIAL — only `instr_ready` / `stream_ready` polled; `addr_ram`, `addr_devmem`, `addr_l2`, `dma_len` never verified by read |
| AXI-Stream write handshake | `test_data_integrity` (sizes 16, 64) | ✓ COVERED |
| AXI-Stream back-pressure | **MISSING** | `m00_axis_tready=0` stall path not tested |
| Mode 3 COMPUTE (tpu.sv FSM) | `test_tpu_compute` (new, Part C) | PARTIAL — test added; depends on mode 4 IRAM write (see known issues) |
| Mode 4 WRITE_IRAM (AXI-Stream) | **MISSING** | No system-level IRAM write test; see **Known Issue** below |
| tensorcore HALT execution | `test_tensorcore::test_tensorcore_halt` | ✓ COVERED |
| tensorcore VLOAD dispatch | `test_tensorcore::test_tensorcore_vload_vhalt` | PARTIAL — only checks completion, not data |
| tensorcore VLOAD→VSTORE data flow | `test_tensorcore::test_tensorcore_vpu_data_flow` (new) | ✓ COVERED (identity) |
| vpu_simd VLOAD data correctness | `test_vpu_simd::test_vpu_simd_data_correctness` (new) | ✓ COVERED |
| vpu_simd VSTORE data correctness | `test_vpu_simd::test_vpu_simd_data_correctness` (new) | ✓ COVERED |
| vpu_simd VADD correctness (FP32 bit-exact) | `test_vpu_simd::test_vpu_simd_data_correctness` (new) | ✓ COVERED |
| vpu_simd VCOMPUTE scalar broadcast | `test_vpu_simd::test_vcompute_scalar_broadcast` | PARTIAL — timing only, data values not verified |
| FP32 addition correctness | `test_fp32_add`, `test_vpu_simd_data_correctness` | ✓ COVERED |
| FP32 multiplication correctness | `test_fp32_mul` | ✓ COVERED |
| MXU matmul correctness | `test_mxu` | PARTIAL — correctness not verified, only completion |
| Systolic array correctness | `test_systolic_array` | ✓ COVERED (100 random cases) |
| decoder field layout [63:62] (hw) | `test_decoder` | ✓ COVERED |
| decoder field layout [63:60] (compiler) | `test_isa_decoder` | ✓ COVERED |
| Reset from non-IDLE mode | **MISSING** | Mid-transfer reset behavior not tested |
| FSM invalid mode (mode > 8) | **MISSING** | RTL behavior undefined |
| Write-after-write to same BRAM addr | **MISSING** | Port A/B conflict behavior not tested |

---

## Known Issues and Gaps

### 1. Mode 3 COMPUTE — No system-level test (critical)

The `tpu.sv` FSM mode 3 (`MODE_COMPUTE`) has never been exercised in simulation.
`test_tpu_compute.py` (added in Part C) covers this gap but depends on mode 4 (see below).

### 2. Mode 4 WRITE_IRAM — Off-by-one timing bug

**Symptom:** Multi-instruction IRAM programs do not load correctly when written via
mode 4 AXI-Stream.

**Root cause:** In `tpu.sv`, the `iram_addr` counter and the `blk_mem_gen_1` write both
fire at the same posedge. The BRAM model captures `addra` using the pre-NBA value of
`iram_addr`, so instruction N is always written to the address that was set at the
**previous** odd write-pointer position:

```
write_pointer=1: BRAM write at addr=0 (pre-NBA=reset=0) ← instr 0, correct
write_pointer=3: BRAM write at addr=0 (pre-NBA=0)       ← instr 1 overwrites addr 0!
write_pointer=5: BRAM write at addr=1 (pre-NBA=1)       ← instr 2 at addr 1 (should be 2)
```

**Workaround:** Set `addr_ram = 1` (not 0) when loading a multi-instruction program.
This makes the IRAM address counter produce the correct pre-NBA address for each
instruction at the write posedge:

```
addr_ram=1:
  write_pointer=1: pre-NBA addr=0          → instr 0 at addr 0 ✓
  write_pointer=3: pre-NBA addr=1+0=1      → instr 1 at addr 1 ✓
  write_pointer=5: pre-NBA addr=1+1=2      → instr 2 at addr 2 ✓
```

`test_tpu_compute.py` uses this workaround. The underlying RTL bug is documented as P3
(fix: update `iram_addr` one cycle before the BRAM write, or use a registered write enable).

### 3. decoder.sv vs compiler ISA field layout mismatch

`decoder.sv` uses `instr[63:62]` for mode (2-bit, hardware decode).
The compiler encodes `instr[63:60]` for type (4-bit, software encode).
These are different contracts that coexist. `test_decoder.py` tests the hardware layout;
`test_isa_decoder.py` tests the compiler layout. The tensorcore bridges them at runtime.
Both are valid for their respective domains.

### 4. AXI-Stream back-pressure (`m00_axis_tready=0`) — not tested

All system tests set `m00_axis_tready=1` permanently. The stall path where the receiver
deasserts `tready` is not exercised. A future test should toggle `tready` mid-burst and
verify no data is lost.

### 5. Reset from non-IDLE mode — undefined behavior

No test exercises `aresetn=0` while a transfer (modes 1–8) is in progress. Partial
writes, pointer corruption, and FSM deadlock are all possible. Behavior is not guaranteed.

---

## Coverage Summary

| Category | Covered | Missing / Partial |
|---|---|---|
| System modes (tpu.sv FSM) | 1, 2, 5, 6, 7, 8 | **3** (COMPUTE), **4** (WRITE_IRAM — known bug) |
| AXI-Lite | write path | read path (addr_ram, addr_devmem, addr_l2 values never read back) |
| AXI-Stream | write handshake, DMA integrity | **back-pressure stall** |
| VPU unit | VLOAD, VSTORE, VCOMPUTE (data) | scalar op impl (NOPs), VMUL data correctness |
| Tensorcore | HALT, VLOAD dispatch, VLOAD→VSTORE identity | MXU dispatch, multi-instruction programs |
| Memory hierarchy | L1, L2, DevMem block copies | L1↔L2 in-kernel (ISA-driven, future) |
| RTL edge cases | — | reset mid-transfer, invalid mode, BRAM port conflict |
