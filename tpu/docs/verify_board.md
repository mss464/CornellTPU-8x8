# Board Verification

> Board-level test specifications and known hardware issues.

---

## Known Issues

### Issue 1: IRAM `addr_ram=1` Workaround (Sim-Only)

**Symptom:** When loading N instructions starting at IRAM[0] via mode 4 (WRITE_IRAM) using the AXI-Stream path, setting `addr_ram=0` causes instructions 1 through N-1 to be written at incorrect IRAM addresses — specifically, each instruction is written to the address one lower than intended.

**Root cause:** In `tpu.sv`, the `iram_addr` counter and `blk_mem_gen_1` write enable (`wea`) both fire at the same `posedge clk`. The BRAM behavioral model (`blk_mem_models.sv`) captures `addra` using the pre-NBA (pre-non-blocking-assignment) value of `iram_addr` — the value that was stable before the current clock edge's assignments resolved. On the first odd `write_pointer_stream` cycle (which triggers the first BRAM write), the pre-NBA `iram_addr` is the value from the previous cycle, not the value being assigned in this cycle.

**Detailed trace with `addr_ram=0`:**
```
write_pointer=1: BRAM write at pre-NBA addr=0   → instr 0 at IRAM[0]  (correct)
write_pointer=3: BRAM write at pre-NBA addr=0   → instr 1 at IRAM[0]  (WRONG: overwrites instr 0)
write_pointer=5: BRAM write at pre-NBA addr=1   → instr 2 at IRAM[1]  (should be IRAM[2])
write_pointer=7: BRAM write at pre-NBA addr=2   → instr 3 at IRAM[2]  (should be IRAM[3])
```

**Workaround:** Set `addr_ram=1` (not 0) when loading N instructions starting at IRAM[0]. With `addr_ram=1`, the pre-NBA address sequence produces the correct 0-based addresses:
```
addr_ram=1:
  write_pointer=1: pre-NBA iram_addr = 1+0 = 0  → instr 0 at IRAM[0]  (correct)
  write_pointer=3: pre-NBA iram_addr = 1+0 = 1  → instr 1 at IRAM[1]  (correct)
  write_pointer=5: pre-NBA iram_addr = 1+1 = 2  → instr 2 at IRAM[2]  (correct)
  write_pointer=7: pre-NBA iram_addr = 1+2 = 3  → instr 3 at IRAM[3]  (correct)
```

**Application in tests:** `test_tpu_compute.py` applies this workaround in `TpuComputeDriver.write_iram()` at line 52: `await self.write_axi_lite(0x0C, 1)`. The module docstring (lines 6–14, referenced at line 14) documents the full analysis.

**Status:** Sim-only timing artifact of the cocotb VPI write coinciding with the BRAM posedge sampling. In synthesis, the BRAM IP captures the address combinationally before posedge (registered output mode). Tracked as P3 (low priority) — fix: update `iram_addr` one cycle before the BRAM write enable, or use a registered write enable.

---

### Issue 2: Bug A — `tpu_slave_axi_stream` IDLE→WRITE_FIFO Reset Stall (Historically Fixed 2026-02-25)

**Symptom:** On the `IDLE→WRITE_FIFO` transition, the `reset` register stayed HIGH for one extra cycle due to a structural NBA ordering issue, causing `write_pointer_stream` to remain at 0 for two cycles. The second incoming word overwrote BRAM address 0, losing the first word.

**Root cause:** The AXI-Stream FSM has a structural anti-pattern where the `else` branch (which should clear `reset`) lacks `begin`/`end`:
```verilog
if (!ARESETN) begin
  state <= IDLE;
end
else            // ← no begin/end
  reset <= 1'b0;
case (state)
  IDLE: begin
    reset <= 1'b1;  // ← NBA in IDLE case overrides the else-reset
    if (start) ...
  end
endcase
```
On the IDLE→WRITE_FIFO transition, the IDLE case still assigns `reset <= 1'b1` as an NBA. Block 1 (which checks `if (!ARESETN || reset)`) fires the reset branch on the first cycle of WRITE_FIFO.

**Fix:** Explicit `reset <= 1'b0` inside the IDLE→WRITE_FIFO transition branch (last NBA wins). Applied in `tpu_slave_axi_stream.v` line 123.

**Regression test:** `test_slave_write_n8` in `test_slave_stream.py` asserts that address 0 is written exactly once. `test_boundary_n8`, `test_boundary_n9`, `test_boundary_n16` in `test_tpu.py` assert that the first element equals 0.0 (Bug A assertion).

**Status:** FIXED. All regression tests pass as of 2026-02-25.

---

### Issue 3: Bug B — `tpu_master_axi_stream` Last FIFO Word Duplicate Reanalysis (2026-02-27)

**Symptom (initially reported):** The last word in a FIFO drain sequence was suspected to be duplicated at the N=8 boundary — specifically, `valid_d1` (the one-cycle delayed version of `axis_tvalid`) might cause `rd_data` to be sampled twice for the last FIFO word.

**Reanalysis conclusion (2026-02-27):** Bug B does NOT exist. `valid_d1` and `rd_data` are inherently aligned because `rd_data` is registered from `fifo_rd_data` at the same posedge that `valid_d1` captures `axis_tvalid`. The timing is:
```
Cycle N:   fifo_rd_en=1     → fifo_rd_data latched at posedge N+1
Cycle N:   axis_tvalid=1    → valid_d1 latched at posedge N+1
Cycle N+1: M_AXIS_TDATA = rd_data (latched from fifo_rd_data)
Cycle N+1: M_AXIS_TVALID = valid_d1
```
Both signals advance in lockstep. The final BRAM word is not duplicated.

**Test evidence:** `test_boundary_n8`, `test_boundary_n9`, `test_boundary_n16` in `test_tpu.py` all assert `result[i] != result[i+1]` (no adjacent duplicates). These tests pass cleanly in simulation.

**Status:** NOT A BUG (reanalysis complete). The original concern was a false positive from an earlier analysis of a different timing diagram.

---

### Issue 4: Board +2 Word Shift in DMA Reads (Open)

**Symptom:** In board smoke tests (`demos/programs/smoke_board.tu`), DMA reads return data with a +2 word offset compared to what was written. The correct pattern is shifted by exactly 2 words.

**Root cause (suspected):** The Vivado block RAM IP (`blk_mem_gen_0`) is configured with output-register mode enabled, producing 2 pipeline stages total (1-cycle address → 1-cycle output register) instead of the 1-cycle latency modeled in simulation (`blk_mem_models.sv`). The `tpu_master_axi_stream` module is compiled with `BRAM_READ_LATENCY = 1` and `count <= 8` (not `< 8`) in the `INIT_COUNTER` prefill window. With 2-cycle synthesis latency, the prefill should use a window of `count <= 9` and `M_AXIS_TDATA` would arrive 1 cycle later, explaining a +2 word offset.

**Simulation status:** All 11 system simulation tests pass (1-cycle latency model is correct for sim).

**Resolution:** Rebuild bitstream with BRAM IP configured for 1-cycle output latency (no output register stage), or update `BRAM_READ_LATENCY` and the `count <= 8` window to match the 2-cycle synthesis latency.

**Status:** OPEN. Tracked in `PLAN.md`. Board smoke test (`smoke_board.tu`) reproduces the shift. No bitstream rebuild yet.

---

## Board Test Harness

The board verification framework consists of **12 offline board tests** located in `tpu/board_tests/`. These tests are designed to run on the Ultra96-V2 FPGA platform via PYNQ, providing end-to-end validation of the TPU system design on physical hardware.

**Key characteristics:**
- **Platform:** PYNQ on Ultra96-V2 FPGA
- **Test location:** `tpu/board_tests/`
- **Number of tests:** 12 test suites
- **Execution:** Run via PYNQ host interface to the loaded bitstream
- **Coverage:** DMA transfers, compute kernels, L2 transfers, and system integration

The board tests exercise the full hardware stack including register access, DMA operations, instruction execution, and data movement across the memory hierarchy — providing validation that cannot be obtained from simulation alone.

---

## Cross-References

See [verify_overview.md](verify_overview.md) for the full module coverage matrix.
