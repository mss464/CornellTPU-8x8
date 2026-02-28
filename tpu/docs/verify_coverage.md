# Verification Coverage Data

> Line coverage data collection and Verilator coverage procedure.

---

## Verilator Coverage Flow

The compute_tile verification suite supports automated line and toggle coverage collection via **Verilator** with **lcov/genhtml** reporting. Coverage is enabled through the `coverage_reports` make target in the compute_tile Makefile.

### RUN_COV Macro

The `RUN_COV` macro (defined in `tpu/verification/compute_tile/Makefile`) orchestrates the coverage collection process:

**Parameters:**
1. **TOPLEVEL** — The Verilog top-level module name being tested
2. **TEST_MODULE** — The cocotb test module name (e.g., `test_fifo4`)
3. **VERILOG_SOURCES** — Comma-separated list of source files to instrument

**Process:**
1. Clears any stale `coverage.dat` file
2. Invokes the cocotb Makefile with Verilator backend
3. Passes `--coverage --coverage-line --coverage-toggle` flags to Verilator
4. Runs the specified test under Verilator with coverage instrumentation enabled
5. Collects the generated `coverage.dat` file
6. Moves the `.dat` file to `coverage/test_module.dat` for later merging

**Coverage metrics:**
- **Line coverage:** Which lines of RTL were executed
- **Toggle coverage:** Which signals changed state during the test

### Coverage Collection Targets

The `coverage_reports` target runs the `RUN_COV` macro for each unit test:
- `test_fifo4` (FIFO module)
- `test_decoder` (instruction decoder)
- `test_isa_decoder` (ISA-level decoder validation)
- `test_pc` (program counter)
- `test_vadd` (vector add operation)
- `test_fp32_add` (IEEE-754 FP32 adder)
- `test_fp32_mul` (IEEE-754 FP32 multiplier)
- `test_pe` (processing element)
- `test_vpu_op` (VPU operations)
- `test_vec_regfile` (vector register file)
- `test_vpu_simd` (SIMD VPU controller)
- `test_systolic_array` (systolic array)
- `test_mxu` (matrix unit)

After all individual test coverages are collected, the macro **merges all `.dat` files** using `verilator_coverage`, generates an `lcov` `.info` file, and produces an **HTML report** with `genhtml`.

### Coverage Output Location

Generated coverage reports are located at:
```
verification/compute_tile/coverage/html/index.html
```

This HTML report provides:
- Per-file coverage summaries
- Per-line coverage highlighting (covered/uncovered/partial)
- Per-signal toggle statistics
- Clickable module hierarchy for drill-down analysis

### System Test Coverage

**Note:** System-level tests in `tpu/verification/system/` (e.g., `test_data_integrity_rtl`, `test_device_mem`, `test_l2_tile`, `test_tpu_compute`) do not currently generate Verilator coverage reports. System tests use cocotb with Icarus Verilog, which does not produce coverage data. Coverage collection is limited to the compute_tile unit tests listed above.

### Building Coverage Reports

```bash
cd tpu/verification/compute_tile
make coverage_reports    # Build all coverage data and HTML report
# Or use the backward-compatible alias:
make coverage_all
```

This target:
1. Clears old coverage data
2. Runs each unit test under Verilator with `--coverage` flags
3. Merges all `.dat` files
4. Generates the HTML report
5. Prints the output location: `verification/compute_tile/coverage/html/index.html`

---

## Cross-References

See [verify_overview.md](verify_overview.md) for the coverage gaps summary and module-by-module test status.
