# Makefile for TPU System RTL Tests
IVERILOG = iverilog
VVP = vvp
COCOTB_LIBS = $(shell python3 -c "import cocotb; import os; print(os.path.join(os.path.dirname(cocotb.__file__), 'libs'))")

SIM_BUILD = sim_build
WAVEFORMS = waveforms

export COCOTB_REDUCED_LOG_FMT = 1
export PYTHONPATH := $(PWD):$(PYTHONPATH)
export PYGPI_PYTHON_BIN = $(shell python3 -c "import sys; print(sys.executable)")

IVFLAGS = -g2012 -Wall

SRC_TPU = ../../src/system/tpu.sv \
          ../../src/system/tpu_master_axi_stream.v \
          ../../src/system/tpu_slave_axi_lite.v \
          ../../src/system/tpu_slave_axi_stream.v \
          ../../src/system/fifo4.sv \
          ../../src/system/device_mem.sv \
          ../../src/l2_tile/l2_tile.sv \
          ../../src/l2_tile/tma_engine.sv
SRC_COMPUTE_TILE = ../../src/compute_tile/compute_tile.sv \
                   ../../src/compute_tile/tensorcore.sv \
                   ../../src/compute_tile/l1.sv \
                   ../../src/compute_tile/mxu.sv \
                   ../../src/compute_tile/systolic.sv \
                   ../../src/compute_tile/pe.sv \
                   ../../src/compute_tile/vpu_simd.sv \
                   ../../src/compute_tile/vpu_op.sv \
                   ../../src/compute_tile/vec_regfile.sv \
                   ../../src/compute_tile/pc.sv \
                   ../../src/compute_tile/decoder.sv \
                   ../../src/compute_tile/fp32_add.sv \
                   ../../src/compute_tile/fp32_mul.sv \
                   ../compute_tile/wrappers/blk_mem_models.sv

SRC_ALL = $(SRC_TPU) $(SRC_COMPUTE_TILE)

# TESTCASE=<name> selects a single cocotb test (e.g. TESTCASE=test_boundary_n8)
# VCD=1 enables waveform dump to dump.vcd (via -DVCD_DUMP compile flag)
COCOTB_TESTCASE_ENV = $(if $(TESTCASE),COCOTB_TESTCASE=$(TESTCASE))
IVFLAGS_VCD         = $(if $(VCD),-DVCD_DUMP -s vcd_dump)

test_data_integrity_rtl: $(SIM_BUILD)
	@echo "=== Running Data Integrity RTL Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s tpu $(IVFLAGS) $(IVFLAGS_VCD) $(SRC_ALL)
	MODULE=test_tpu COCOTB_TEST_MODULES=test_tpu $(COCOTB_TESTCASE_ENV) $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@echo "=== Data Integrity RTL Test Complete ==="

test_device_mem: $(SIM_BUILD)
	@echo "=== Running Device Memory Tests ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s tpu $(IVFLAGS) $(IVFLAGS_VCD) $(SRC_ALL)
	MODULE=test_device_mem COCOTB_TEST_MODULES=test_device_mem $(COCOTB_TESTCASE_ENV) $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@echo "=== Device Memory Tests Complete ==="

test_l2_tile: $(SIM_BUILD)
	@echo "=== Running L2 Tile Tests ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s tpu $(IVFLAGS) $(IVFLAGS_VCD) $(SRC_ALL)
	MODULE=test_l2_tile COCOTB_TEST_MODULES=test_l2_tile $(COCOTB_TESTCASE_ENV) $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@echo "=== L2 Tile Tests Complete ==="

test_tpu_compute: $(SIM_BUILD)
	@echo "=== Running TPU Compute Mode Tests ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s tpu $(IVFLAGS) $(IVFLAGS_VCD) $(SRC_ALL)
	MODULE=test_tpu_compute COCOTB_TEST_MODULES=test_tpu_compute $(COCOTB_TESTCASE_ENV) $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@echo "=== TPU Compute Mode Tests Complete ==="

$(SIM_BUILD):
	mkdir -p $(SIM_BUILD)
	mkdir -p $(WAVEFORMS)

clean:
	rm -rf $(SIM_BUILD) $(WAVEFORMS)/*.vcd results.xml __pycache__ *.vcd
