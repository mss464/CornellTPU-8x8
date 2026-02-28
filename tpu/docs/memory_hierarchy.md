# TPU Memory Hierarchy — Design Reference

> **Status:** P1 single-tile implementation
> **Last updated:** 2026-02-26
> **Audience:** Human reviewers debugging board-level timing issues

---

## 1. Overview

```
Host (DDR / PYNQ)
       │  AXI-Stream DMA  (modes 1, 2, 4)
       ▼
Device Memory  (blk_mem_gen_2)   256 KiB  65536 × 32-bit
       │  tma_engine  (modes 5, 6 / TMA instruction)
       ▼
L2 SRAM        (blk_mem_gen_3)   128 KiB  32768 × 32-bit
       │  tpu.sv FSM direct port control  (modes 7, 8)
       ▼
L1 Data BRAM   (blk_mem_gen_0)    32 KiB   8192 × 32-bit
       │  compute tile internal bus
       ▼
Compute (MXU, VPU)

IRAM           (blk_mem_gen_1)     2 KiB    256 × 64-bit
       │  tensorcore fetch
       ▼
Decoder → Dispatch
```

All four BRAMs are **true dual-port** (TDP) Xilinx Block RAM IPs.
All four are clocked by `s00_axi_aclk` (= the single TPU system clock).

---

## Related Documents

- [BRAM Specifications](bram_specs.md) — component details, latency invariant, sim/HW alignment
- [Data Movement Modes](data_movement.md) — modes 1–8, cycle traces, TMA instruction flow
- [Board Bug Analysis](board_bugs.md) — DMA corruption root causes, fix strategy
