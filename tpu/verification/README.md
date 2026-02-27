# Mini-TPU Verification Suite

Verification is organized by subsystem. All tests use **cocotb + Icarus Verilog** (RTL simulation).
BRAM IPs are replaced by `wrappers/blk_mem_models.sv` (1-cycle latency behavioral model).

Run from the project root:

```bash
make -C tpu smoke-sim        # system tests only (fastest)
make -C tpu smoke-sim-full   # system + compute unit tests
```

---

## 1. System Tests (`system/`)

| Test file | Make target | DUT | What it covers |
|-----------|-------------|-----|----------------|
| `test_tpu.py` | `test_data_integrity_rtl` | `tpu` (full top) | Host→DevMem→Host DMA roundtrip. Modes 1/2. |
| `test_device_mem.py` | `test_device_mem` | `tpu` | Device memory read/write with base-address offset. |
| `test_l2_tile.py` | `test_l2_tile` | `tpu` | L2 tile block copies: modes 5/6 (DM↔L2), modes 7/8 (L2↔L1). |

### `test_tpu.py` — test cases

| Test function | N | Bug caught | Description |
|---------------|---|------------|-------------|
| `test_data_integrity` | 16, 64, 8 (known values) | general | Sequential ramp and known-value roundtrip; element-by-element equality. |
| `test_boundary_n8` | 8 | Bug A + Bug B | N = FIFO depth. Full FIFO drain. Checks `result[0]==0`, no adjacent duplicates, exact equality. |
| `test_boundary_n9` | 9 | Bug B | N = FIFO depth + 1. Prefill-to-steady-state transition. Checks for word-7 duplicate. |
| `test_boundary_n16` | 16 | Bug A + Bug B | Explicit boundary assertions on the standard size. |

**Paths exercised by system tests:**

```
host AXI-Lite write → tpu.sv FSM → mode 1 (WRITE_DEVMEM)
  → tpu_slave_axi_stream: IDLE → WRITE_FIFO (fifo_wren, data_valid)
  → device_mem Port A write (wea = data_write_en && stream_data_valid)

host AXI-Lite write → tpu.sv FSM → mode 2 (READ_DEVMEM)
  → device_mem Port A read (1-cycle BRAM latency)
  → tpu_master_axi_stream: IDLE → INIT_COUNTER (prefetch 8 words) → SEND_STREAM
    → fifo4 drain (valid_d1 && !fifo_empty → M_AXIS_TVALID)
  → host AXI-Stream master output

mode 5 (DM→L2): device_mem Port B → l2_tile Port B (tma_engine)
mode 6 (L2→DM): l2_tile Port B → device_mem Port B
mode 7 (L2→L1): l2_tile Port A (1-cycle) → compute_tile L1 DMA write
mode 8 (L1→L2): compute_tile L1 DMA read → l2_tile Port A write
```

### `test_device_mem.py` — test cases

| Test function | Description |
|---------------|-------------|
| `test_device_mem_basic` | Single-word write/read at addr 0. |
| `test_device_mem_sequential` | Sequential ramp write/read at addr 0. |
| `test_device_mem_base_addr` | Non-zero base address offset (addr_devmem ≠ 0). |
| `test_device_mem_pattern` | Non-sequential known-value pattern. |

### `test_l2_tile.py` — test cases

| Test function | Description |
|---------------|-------------|
| `test_dm_to_l2` | Mode 5: block copy from device memory to L2. Verifies l2_tile tma_engine. |
| `test_l2_to_dm` | Mode 6: block copy from L2 to device memory. |
| `test_l2_to_l1` | Mode 7: L2→L1 burst; reads from L2 Port A (1-cycle BRAM latency) into compute_tile L1. |
| `test_l1_to_l2` | Mode 8: L1→L2 burst; reads from L1 DMA port into L2 Port A. |
| `test_hierarchy_roundtrip` | DM→L2→L1→L2→DM end-to-end hierarchy traversal. |

---

## 2. Compute Unit Tests (`compute_tile/`)

| Test file | Make target | DUT | What it covers |
|-----------|-------------|-----|----------------|
| `test_decoder.py` | `test_decoder` | `decoder` | All ISA opcodes; immediate encoding; immediate sign extension. |
| `test_fifo4.py` | `test_fifo4` | `fifo4` | Empty/full flags; `one_item_remaining`; wraparound; overflow guard. |
| `test_fp32_add.py` | `test_fp32_add` | `fp32_add` | IEEE-754 FP32 add: normal, zero, large magnitude. |
| `test_fp32_mul.py` | `test_fp32_mul` | `fp32_mul` | IEEE-754 FP32 mul: normal, zero, identity. |
| `test_mxu.py` | `test_mxu` | `mxu` (+ `blk_mem_gen_0`) | MXU reads L1, drives systolic array; output accumulation. |
| `test_pe.py` | `test_pe` | `pe` | Single PE: multiply-accumulate; reset; accumulate chain. |
| `test_systolic_array.py` | `test_systolic_array` | `systolic` | 4×4 systolic matmul; known-value golden check. |
| `test_tensorcore.py` | `test_tensorcore` | `compute_tile` (full) | Fetch/decode/dispatch loop; HALT; TMA instruction issue. |
| `test_vpu_op.py` | `test_vpu_op` | `vpu_op` | Per-lane ops: add, mul, relu, move. |
| `test_vpu_simd.py` | `test_vpu_simd` | `vpu_simd` | 8-lane SIMD dispatch; vector register file write-back. |
| `test_vec_regfile.py` | `test_vec_regfile` | `vec_regfile` | 8×8 register file: write then read all lanes/registers. |

---

## 3. Known Simulation Gaps

| Gap | Status | Notes |
|-----|--------|-------|
| Bug A (slave wea spurious write at addr 0) | **FIXED** (P1.4) | `stream_data_valid` gate added; `test_boundary_n8/n16` catch regression. |
| Bug B (master TVALID 1-cycle overshoot) | **FIXED** (P1.4) | `valid_d1 && !fifo_empty` gate; `test_boundary_n8/n9` catch regression. |
| Multi-cycle `M_AXIS_TREADY` de-assert | Not tested | Sim always holds `tready=1`; backpressure path untested. |
| IRAM write path (mode 4) | Partially tested | `test_tensorcore` exercises compute path but not the AXI-Stream IRAM load. |
| TMA from tensorcore (ISA instruction) | Tested in `test_tensorcore` | `ct_tma_req` handshake to `l2_tile` verified. |

---

## 4. Adding a New Test

1. Add a `@cocotb.test()` function to the relevant `test_*.py` file.
2. The function name must start with `test_`.
3. cocotb discovers all `@cocotb.test()` functions automatically — no Makefile changes needed.
4. Update this README's test-case table.
