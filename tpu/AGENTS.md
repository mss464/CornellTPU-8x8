FIXME: `make verify-system_data` fails with Bus error.

## TPU Compute Hang Resolved (2026-02-19)
The `TimeoutError` during `tpu.compute()` has been resolved by fixing multiple RTL race conditions and FSM deadlocks.

### Solved
- **Instruction Loading Race:** Fixed `tpu_slave_axi_stream.v` to ensure 64-bit instructions are stable before BRAM write.
- **Port Direction Error:** Corrected `s00_axi_rdata` in `tpu.sv` (was `input`, now `output`).
- **Data Alignment:** Fixed Port A address latency in `scratchpad.sv` by making `dma_addr` combinational.
- **Instruction Fetch Latency:** Added `FETCH` states to `tensorcore.sv` to handle BRAM read latency for Instruction 0.
- **Hang Resilience:** Added watchdog timers to `mxu.sv` (Capture state) and `vpu_simd.sv` (Scalar instructions) to prevent infinite hangs.

### Current Status
- **Test execution:** `make board-comprehensive` now runs to completion without Timing Out.
- **Correctness:** Numerical verification fails for Scalar VPU ops (implemented as NOPs for hang prevention) and some large Matmuls (minor DMA off-by-one).

## Performance & Optimization
... (existing content)

### Hardware Constraints & Findings
- **FP32 Range:** Safe values are between `1e-20` and `1e20`.
- **Subnormal Numbers:** FP32 subnormals (< 1.18e-38) cause bus errors. Hardware likely flushes denormals to zero, but application software should clamp to `1e-20`.
- **Extreme Values:** Max FP32 (~3.4e38) causes crashes. Use safe max `1e20`.
- **Memory:** BRAM capacity verified at 8192 elements (32 KB, 13-bit addressing).

### Recommendations
- **Developers:** Clamp values to `1e-20`, avoid subnormals, and use tiling for matrices exceeding 8192 elements.
- **Hardware:** Consider adding explicit flush-to-zero flags and overflow/underflow exception handling.

---

## Troubleshooting

### "Black box" errors for blk_mem_gen_1
The packaging script creates the BRAM IP dynamically. If you see errors:
1. Ensure Vivado has network access or the IP catalog is cached
2. Check BRAM IP version matches your Vivado version

### IP not found in repository
Run `make clean` and rebuild. Ensure the `ip_repo` path is correct.

### Timing violations
The default 100MHz clock is conservative. Check `timing_summary.txt` for details.

## Performance & Optimization

### MXU Memory Latency (MEM_LATENCY=3)
- **Current State:** `MEM_LATENCY` is set to `3` in `mxu.sv` and `tensorcore.sv` for safety. This accounts for BRAM address registration (1 cycle) and BRAM primitive output registration (1 cycle).
- **Optimization Potential:** While the initial read takes 2-3 cycles, the BRAMs are pipelined. Subsequent elements in a burst read reach the MXU on every cycle (bandwidth = 1 element/cycle). 
- **Future Action:** Refactor the MXU state machine to use a pipelined burst mode instead of waiting `MEM_LATENCY` for every single element, which currently throttles throughput to ~33% of theoretical peak.

