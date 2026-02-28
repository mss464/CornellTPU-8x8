# Verification: pc.sv

**Role:** Program counter. Supports reset, increment, conditional hold, and load (jump) operations. Used by `tensorcore.sv` to sequence through IRAM instructions.

**Test files:**
- `tpu/verification/compute_tile/test_pc.py` — 6 dedicated unit tests

**Test functions exercising this module:**

| Test function | Coverage |
|---|---|
| `test_pc_reset` | PC = 0 after reset |
| `test_pc_increment` | PC increments by 1 on each enable cycle |
| `test_pc_load` | PC jumps to loaded value when load signal asserted |
| `test_pc_hold` | PC holds current value when hold signal asserted |
| `test_pc_load_priority` | Load takes priority over increment |
| `test_pc_wrap_around` | PC wraps from max (255) to 0 |

**Coverage details:**
- All four operational modes: reset, increment, hold, load
- Load priority over increment
- 8-bit wrap-around at address 255

**Known coverage gaps:**
- `hold` and `load` simultaneously asserted (priority undefined)
- PC used inside a multi-instruction kernel is exercised implicitly in system tests but the PC value is not directly observable from the system test bench
