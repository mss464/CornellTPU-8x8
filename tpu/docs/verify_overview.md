# Verification Overview

> Per-module verification specs are in individual `verify_<module>.md` files.
> See also: [verify_board.md](verify_board.md) — board tests, [verify_coverage.md](verify_coverage.md) — coverage data.

---

## Contents

This document provides a high-level overview of the verification infrastructure for the Mini-TPU project. Detailed module-specific verification specs have been split into per-module files:

1. **System-Level Modules**
   - [verify_tpu_system.md](verify_tpu_system.md) — tpu.sv top, dma_engine, compute_ctrl, l2_ctrl, concurrent execution
   - [verify_slave_stream.md](verify_slave_stream.md) — AXI-Stream sink + AXI-Lite register slave
   - [verify_master_stream.md](verify_master_stream.md) — AXI-Stream source (DMA read path)
   - [verify_fifo4.md](verify_fifo4.md) — synchronous FIFO
   - [verify_device_mem.md](verify_device_mem.md) — device memory BRAM

2. **Tile-Level Modules**
   - [verify_l2_tile.md](verify_l2_tile.md) — L2 SRAM tile + TMA engine
   - [verify_tensorcore.md](verify_tensorcore.md) — instruction fetch/dispatch + compute_tile + l1
   - [verify_tpu_compute.md](verify_tpu_compute.md) — compute mode end-to-end (mode 3)

3. **Compute Tile Sub-Modules**
   - [verify_decoder.md](verify_decoder.md) — ISA instruction decoder
   - [verify_mxu.md](verify_mxu.md) — matrix unit controller
   - [verify_systolic.md](verify_systolic.md) — systolic array tile
   - [verify_pe.md](verify_pe.md) — processing element (MAC)
   - [verify_vpu_simd.md](verify_vpu_simd.md) — SIMD vector unit
   - [verify_vpu_op.md](verify_vpu_op.md) — per-lane vector operations
   - [verify_vec_regfile.md](verify_vec_regfile.md) — vector register file
   - [verify_fp32_add.md](verify_fp32_add.md) — FP32 adder
   - [verify_fp32_mul.md](verify_fp32_mul.md) — FP32 multiplier
   - [verify_pc.md](verify_pc.md) — program counter

---

## Test Infrastructure

**Simulation Framework:** cocotb + Icarus Verilog

- All unit tests and system integration tests run under cocotb
- FPGA IP blocks (BRAM, FIFO) are replaced by behavioral models in `wrappers/blk_mem_models.sv`
- Results reported in `results.xml` (JUnit format)

**BRAM Behavioral Model:**
- Location: `tpu/verification/compute_tile/wrappers/` (split into `bram_l1_data.sv`, `bram_iram.sv`, `bram_device_mem.sv`, `bram_l2_sram.sv`)
- Latency: 1 cycle (address captured on posedge → data valid next posedge)
- Replaces: `blk_mem_gen_0` (Data BRAM), `blk_mem_gen_1` (IRAM), `blk_mem_gen_2` (Device Mem), `blk_mem_gen_3` (L2)

**Running Tests:**
```bash
cd tpu

# Smoke test (quick PASS/FAIL)
make smoke-sim              # 3 system tests
make smoke-sim-full         # + compute unit tests

# Specific test suites
cd verification/system
make test_data_integrity_rtl # System integration integrity
make test_device_mem         # Device memory
make test_l2_tile            # L2 tile
make test_tpu_compute        # Compute mode end-to-end

cd verification/compute_tile
make test_<module>          # e.g., make test_mxu, make test_systolic_array
```

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
