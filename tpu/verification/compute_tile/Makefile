#==============================================================================
# Mini-TPU RTL Unit Test Makefile
# Run from: tests/tpu/
# Usage: make test_<module> or make all
#==============================================================================

# Compiler and simulator settings
IVERILOG = iverilog
VVP = vvp
# cocotb 2.0+ path detection
COCOTB_LIBS = $(shell python3 -c "import cocotb; import os; print(os.path.join(os.path.dirname(cocotb.__file__), 'libs'))")

# Directories
TPU_DIR = ../../src/compute_tile
SIM_BUILD = sim_build
WAVEFORMS = waveforms
WRAPPERS = wrappers

# Environment variables for cocotb
export COCOTB_REDUCED_LOG_FMT = 1
export LIBPYTHON_LOC = $(shell python3 -c "import find_libpython; print(find_libpython.find_libpython())")
export PYTHONPATH := $(PWD):$(PYTHONPATH)
export PYGPI_PYTHON_BIN = $(shell which python3)

# cocotb v1.x expects MODULE, v2.x accepts COCOTB_TEST_MODULES.
# Normalize on MODULE while keeping COCOTB_TEST_MODULES for compatibility.
COCOTB_MODULE ?= $(COCOTB_TEST_MODULES)

# Iverilog flags
IVFLAGS = -g2012 -Wall

# Default simulator for normal tests
SIM ?= iverilog

# Coverage (Verilator + lcov/genhtml)
VERILATOR = verilator
VERILATOR_COVERAGE = verilator_coverage
GENHTML = genhtml
COCOTB_MAKEFILES = $(shell python3 -c "import cocotb, os; print(os.path.join(os.path.dirname(cocotb.__file__), 'share', 'makefiles'))")
COCOTB_PYTHONPATH = $(shell python3 -c "import cocotb, os; print(os.path.dirname(os.path.dirname(cocotb.__file__)))")
COV_DIR = coverage
COV_INFO = $(COV_DIR)/coverage.info
COV_HTML = $(COV_DIR)/html
VERILATOR_ROOT ?= /home/lan64/verilator

#==============================================================================
# RTL Source Files (grouped by category)
#==============================================================================

# Core arithmetic
SRC_FP32 = $(TPU_DIR)/fp32_add.sv $(TPU_DIR)/fp32_mul.sv
# Control and memory
SRC_FIFO = ../../src/system/fifo4.sv
SRC_PC = $(TPU_DIR)/pc.sv
SRC_DECODER = $(TPU_DIR)/decoder.sv
SRC_BRAM = $(TPU_DIR)/scratchpad.sv $(WRAPPERS)/blk_mem_models.sv

# Processing elements
SRC_PE = $(TPU_DIR)/pe.sv $(SRC_FP32)
SRC_SYSTOLIC = $(TPU_DIR)/systolic.sv $(SRC_PE)
SRC_MXU = $(TPU_DIR)/mxu.sv $(SRC_SYSTOLIC)

# VPU
SRC_VPU_OP = $(TPU_DIR)/vpu_op.sv $(SRC_FP32)
SRC_VPU = $(TPU_DIR)/vpu.sv $(SRC_VPU_OP)

# VPU SIMD (new)
SRC_VEC_REGFILE = $(TPU_DIR)/vec_regfile.sv
SRC_VPU_SIMD = $(TPU_DIR)/vpu_simd.sv $(SRC_VPU_OP) $(SRC_VEC_REGFILE)

# Integrated Modules
SRC_TENSORCORE = $(TPU_DIR)/tensorcore.sv $(SRC_PC) $(SRC_DECODER) $(SRC_MXU) $(SRC_VPU_SIMD) $(WRAPPERS)/blk_mem_models.sv
SRC_COMPUTE_TILE = $(TPU_DIR)/compute_tile.sv $(SRC_TENSORCORE) $(SRC_BRAM)

# All sources for comprehensive tests (deduplicated)
SRC_CORE = $(SRC_PC) $(SRC_DECODER) $(SRC_FP32)
SRC_TENSORCORE = $(TPU_DIR)/tensorcore.sv \
                 $(TPU_DIR)/mxu.sv \
                 $(TPU_DIR)/systolic.sv \
                 $(TPU_DIR)/pe.sv \
                 $(TPU_DIR)/vpu_simd.sv \
                 $(TPU_DIR)/vpu_op.sv \
                 $(TPU_DIR)/vec_regfile.sv \
                 $(SRC_CORE) \
                 $(WRAPPERS)/blk_mem_models.sv

SRC_COMPUTE_TILE = $(TPU_DIR)/compute_tile.sv $(SRC_TENSORCORE) $(SRC_BRAM)

SRC_ALL = $(SRC_TENSORCORE) $(SRC_FIFO)

#==============================================================================
# Test Targets - Unit Tests for Individual Modules
#==============================================================================

# FIFO unit test
test_fifo4: $(SIM_BUILD)
	@echo "=== Running FIFO4 Unit Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s fifo4 -s dump $(IVFLAGS) \
		$(SRC_FIFO) $(WRAPPERS)/dump_fifo4.sv
	MODULE=test_fifo4 COCOTB_TEST_MODULES=test_fifo4 $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@mv -f fifo4.vcd $(WAVEFORMS)/ 2>/dev/null || true
	@echo "=== FIFO4 Test Complete ==="

# Decoder unit test
test_decoder: $(SIM_BUILD)
	@echo "=== Running Decoder Unit Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s decoder -s dump $(IVFLAGS) \
		$(SRC_DECODER) $(WRAPPERS)/dump_decoder.sv
	MODULE=test_decoder COCOTB_TEST_MODULES=test_decoder $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@mv -f decoder.vcd $(WAVEFORMS)/ 2>/dev/null || true
	@echo "=== Decoder Test Complete ==="

# ISA Decoder test (tests actual instruction encoding per docs/system.md)
test_isa_decoder: $(SIM_BUILD)
	@echo "=== Running ISA Decoder Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s decoder -s dump $(IVFLAGS) \
		$(SRC_DECODER) $(WRAPPERS)/dump_decoder.sv
	MODULE=test_isa_decoder COCOTB_TEST_MODULES=test_isa_decoder $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@mv -f decoder.vcd $(WAVEFORMS)/ 2>/dev/null || true
	@echo "=== ISA Decoder Test Complete ==="

# MXU (Matrix Unit) test (tests for stale weight bug)
test_mxu: $(SIM_BUILD)
	@echo "=== Running MXU Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s mxu $(IVFLAGS) $(SRC_MXU)
	MODULE=test_mxu COCOTB_TEST_MODULES=test_mxu $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@echo "=== MXU Test Complete ==="

# Program Counter unit test
test_pc: $(SIM_BUILD)
	@echo "=== Running PC Unit Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s pc -s dump $(IVFLAGS) \
		$(SRC_PC) $(WRAPPERS)/dump_pc.sv
	MODULE=test_pc COCOTB_TEST_MODULES=test_pc $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@mv -f pc.vcd $(WAVEFORMS)/ 2>/dev/null || true
	@echo "=== PC Test Complete ==="

# Vector Add unit test
test_vadd: $(SIM_BUILD)
	@echo "=== Running VADD Unit Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s vadd -s dump $(IVFLAGS) \
		$(SRC_VADD) $(WRAPPERS)/dump_vadd.sv
	MODULE=test_vadd COCOTB_TEST_MODULES=test_vadd $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@mv -f vadd.vcd $(WAVEFORMS)/ 2>/dev/null || true
	@echo "=== VADD Test Complete ==="

# FP32 Add unit test
test_fp32_add: $(SIM_BUILD)
	@echo "=== Running FP32 Add Unit Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s fp32_add -s dump $(IVFLAGS) \
		$(SRC_FP32) $(WRAPPERS)/dump_fp32_add.sv
	MODULE=test_fp32_add COCOTB_TEST_MODULES=test_fp32_add $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@mv -f fp32_add.vcd $(WAVEFORMS)/ 2>/dev/null || true
	@echo "=== FP32 Add Test Complete ==="

# FP32 Mul unit test
test_fp32_mul: $(SIM_BUILD)
	@echo "=== Running FP32 Mul Unit Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s fp32_mul -s dump $(IVFLAGS) \
		$(SRC_FP32) $(WRAPPERS)/dump_fp32_mul.sv
	MODULE=test_fp32_mul COCOTB_TEST_MODULES=test_fp32_mul $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@mv -f fp32_mul.vcd $(WAVEFORMS)/ 2>/dev/null || true
	@echo "=== FP32 Mul Test Complete ==="

# PE (Processing Element) unit test
test_pe: $(SIM_BUILD)
	@echo "=== Running PE Unit Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s pe $(IVFLAGS) $(SRC_PE)
	MODULE=test_pe COCOTB_TEST_MODULES=test_pe $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@echo "=== PE Test Complete ==="

# VPU operation unit test (requires parameterized_adder/mul wrappers)
test_vpu_op: $(SIM_BUILD)
	@echo "=== Running VPU Op Unit Test ==="
	@echo "Note: vpu_op requires parameterized_adder and parameterized_mul modules"
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s vpu_op -s dump $(IVFLAGS) \
		$(SRC_VPU_OP) $(WRAPPERS)/dump_vpu_op.sv || \
		echo "Warning: vpu_op has dependencies that may need resolution"
	MODULE=test_vpu_op COCOTB_TEST_MODULES=test_vpu_op $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@mv -f vpu_op.vcd $(WAVEFORMS)/ 2>/dev/null || true
	@echo "=== VPU Op Test Complete ==="

# Vector register file unit test
test_vec_regfile: $(SIM_BUILD)
	@echo "=== Running Vector Register File Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s vec_regfile -s dump $(IVFLAGS) \
		$(SRC_VEC_REGFILE) $(WRAPPERS)/dump_vec_regfile.sv
	MODULE=test_vec_regfile COCOTB_TEST_MODULES=test_vec_regfile $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@mv -f vec_regfile.vcd $(WAVEFORMS)/ 2>/dev/null || true
	@echo "=== Vector Register File Test Complete ==="

# SIMD VPU unit test
test_vpu_simd: $(SIM_BUILD)
	@echo "=== Running SIMD VPU Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s vpu_simd -s dump $(IVFLAGS) \
		$(SRC_VPU_SIMD) $(WRAPPERS)/dump_vpu_simd.sv
	MODULE=test_vpu_simd COCOTB_TEST_MODULES=test_vpu_simd $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@mv -f vpu_simd.vcd $(WAVEFORMS)/ 2>/dev/null || true
	@echo "=== SIMD VPU Test Complete ==="

# TensorCore integrated test
test_tensorcore: $(SIM_BUILD)
	@echo "=== Running TensorCore Integrated Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s tensorcore $(IVFLAGS) \
		$(SRC_TENSORCORE)
	MODULE=test_tensorcore COCOTB_TEST_MODULES=test_tensorcore $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@echo "=== TensorCore Test Complete ==="

test_systolic_array: $(SIM_BUILD)
	@echo "=== Running Random Systolic Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s systolic $(IVFLAGS) $(SRC_SYSTOLIC)
	MODULE=test_systolic_array COCOTB_TEST_MODULES=test_systolic_array $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)

#==============================================================================
# Aggregate Test Targets
#==============================================================================

# Core unit tests (fast, independent modules)
test_unit: test_fifo4 test_decoder test_pc test_fp32_add test_fp32_mul test_isa_decoder test_vec_regfile test_vpu_simd
	@echo ""
	@echo "========================================"
	@echo "All unit tests completed successfully!"
	@echo "========================================"

# PE and systolic tests
test_compute: test_pe test_systolic_array
	@echo ""
	@echo "========================================"
	@echo "All compute tests completed successfully!"
	@echo "========================================"

# MXU tests
test_wrappers: test_mxu
	@echo ""
	@echo "========================================"
	@echo "All wrapper tests completed!"
	@echo "========================================"

# Run ALL tests
all: test_unit test_compute
	@echo ""
	@echo "========================================"
	@echo "ALL TESTS PASSED"
	@echo "========================================"

# Comprehensive test
test_all: test_unit test_compute test_wrappers
	@echo ""
	@echo "========================================"
	@echo "COMPREHENSIVE TEST SUITE PASSED"
	@echo "========================================"

#==============================================================================
# Coverage (Verilator) - ALL tests
#==============================================================================

define RUN_COV
	@rm -f coverage.dat
	@$(MAKE) -f $(COCOTB_MAKEFILES)/Makefile.sim \
		SIM=verilator TOPLEVEL_LANG=verilog \
		TOPLEVEL=$(1) MODULE=$(2) \
		VERILOG_SOURCES="$(3)" \
		SIM_BUILD="$(COV_DIR)/build/$(2)" \
		VERILATOR_ROOT="$(VERILATOR_ROOT)" \
		VERILATOR_BIN_DIR="$(VERILATOR_ROOT)/bin" \
		EXTRA_ARGS="--coverage --coverage-line --coverage-toggle" \
		VERILATOR_INCLUDER="env -u PYTHONHOME -u PYTHONPATH -u PYTHONNOUSERSITE /usr/bin/python3 $(VERILATOR_ROOT)/bin/verilator_includer" \
		PYTHON3=/usr/bin/python3 \
		PYTHONPATH="$(COCOTB_PYTHONPATH)" PYTHONNOUSERSITE=1 \
		COCOTB_CONFIG="/usr/bin/python3 -m cocotb.config" \
		LC_ALL=C.UTF-8 LANG=C.UTF-8 \
		VERILATOR_COVERAGE=1
	@mkdir -p $(COV_DIR)
	@if [ -f coverage.dat ]; then \
		mv coverage.dat $(COV_DIR)/$(2).dat; \
	else \
		echo "No coverage.dat generated for $(2)."; exit 1; \
	fi
endef

coverage_reports:
	@mkdir -p $(COV_DIR)
	@rm -rf $(COV_DIR)/build
	$(call RUN_COV,fifo4,test_fifo4,$(SRC_FIFO))
	$(call RUN_COV,decoder,test_decoder,$(SRC_DECODER))
	$(call RUN_COV,decoder,test_isa_decoder,$(SRC_DECODER))
	$(call RUN_COV,pc,test_pc,$(SRC_PC))
	$(call RUN_COV,vadd,test_vadd,$(SRC_VADD))
	$(call RUN_COV,fp32_add,test_fp32_add,$(SRC_FP32))
	$(call RUN_COV,fp32_mul,test_fp32_mul,$(SRC_FP32))
	$(call RUN_COV,pe,test_pe,$(SRC_PE))
	$(call RUN_COV,vpu_op,test_vpu_op,$(SRC_VPU_OP))
	$(call RUN_COV,vec_regfile,test_vec_regfile,$(SRC_VEC_REGFILE))
	$(call RUN_COV,vpu_simd,test_vpu_simd,$(SRC_VPU_SIMD))
	$(call RUN_COV,systolic,test_systolic_array,$(SRC_SYSTOLIC))
	$(call RUN_COV,mxu,test_mxu,$(SRC_MXU))
	
	@echo "=== Merging coverage data ==="
	@COV_DAT=$$(find $(COV_DIR) -name '*.dat' -print); \
	if [ -z "$$COV_DAT" ]; then \
		echo "No coverage data files found. Did Verilator run?"; exit 1; \
	fi; \
	$(VERILATOR_COVERAGE) --write-info $(COV_INFO) $$COV_DAT
	@echo "=== Generating HTML report ==="
	@env -i PATH=/usr/bin:/bin HOME="$$HOME" LANG=C.UTF-8 \
		$(GENHTML) $(COV_INFO) --output-directory $(COV_HTML)
	@echo "Coverage HTML: $(COV_HTML)/index.html"

# Backward-compatible alias
coverage_all: coverage_reports

#==============================================================================
# Infrastructure
#==============================================================================

# Create build directories
$(SIM_BUILD):
	mkdir -p $(SIM_BUILD)
	mkdir -p $(WAVEFORMS)

# Waveform viewing (usage: make show_fifo4)
show_%: $(WAVEFORMS)/%.vcd
	gtkwave $<

# Linting with Verilator
lint:
	verilator --lint-only -Wall $(SRC_ALL) 2>&1 | head -50

# Linting with Verible (if available)
lint_verible:
	verible-verilog-lint $(TPU_DIR)/*.sv --rules_config verible.rules 2>/dev/null || echo "Verible not found"

# Cleanup
clean:
	rm -rf $(SIM_BUILD) $(WAVEFORMS)/*.vcd results.xml __pycache__ *.vcd

# Deep clean (includes pycache)
distclean: clean
	rm -rf __pycache__ .pytest_cache

# Align with c2s2 style
clean_all: distclean

# Help
help:
	@echo "Mini-TPU RTL Test Makefile"
	@echo ""
	@echo "Unit Tests (Individual Modules):"
	@echo "  make test_fifo4       - FIFO unit test"
	@echo "  make test_decoder     - Instruction decoder test"
	@echo "  make test_pc          - Program counter test"
	@echo "  make test_vadd        - Vector add test"
	@echo "  make test_fp32_add    - FP32 adder test"
	@echo "  make test_fp32_mul    - FP32 multiplier test"
	@echo "  make test_vec_regfile - Vector register file test"
	@echo "  make test_vpu_simd    - SIMD VPU test"
	@echo "  make test_pe          - Processing element test"
	@echo "  make test_systolic_array     - Systolic array random test (100 cases)"
	@echo "  make test_mxu             - MXU (matrix unit) sequential test"
	@echo ""
	@echo "Aggregate Test Targets:"
	@echo "  make test_unit        - All unit tests (fast)"
	@echo "  make test_compute     - PE and systolic tests"
	@echo "  make all              - Unit + compute tests"
	@echo "  make test_all         - Comprehensive test suite"
	@echo ""
	@echo "Utilities:"
	@echo "  make lint             - Lint with Verilator"
	@echo "  make show_<module>    - View waveform (e.g., show_fifo4)"
	@echo "  make clean            - Remove build artifacts"
	@echo "  make help             - Show this help"

.PHONY: all clean distclean lint lint_verible help
.PHONY: test_unit test_compute test_wrappers test_all
.PHONY: test_fifo4 test_decoder test_pc test_vadd test_fp32_add test_fp32_mul
.PHONY: test_vec_regfile test_vpu_simd test_pe test_systolic_array test_vpu_op test_isa_decoder test_mxu
