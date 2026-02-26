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
          ../../src/l2_tile/l2_tile.sv
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

test_data_integrity_rtl: $(SIM_BUILD)
	@echo "=== Running Data Integrity RTL Test ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s tpu $(IVFLAGS) $(SRC_ALL)
	MODULE=test_tpu COCOTB_TEST_MODULES=test_tpu $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@echo "=== Data Integrity RTL Test Complete ==="

test_device_mem: $(SIM_BUILD)
	@echo "=== Running Device Memory Tests ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s tpu $(IVFLAGS) $(SRC_ALL)
	MODULE=test_device_mem COCOTB_TEST_MODULES=test_device_mem $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q 'failure' results.xml || (echo "TEST FAILED" && exit 1)
	@echo "=== Device Memory Tests Complete ==="

$(SIM_BUILD):
	mkdir -p $(SIM_BUILD)
	mkdir -p $(WAVEFORMS)

clean:
	rm -rf $(SIM_BUILD) $(WAVEFORMS)/*.vcd results.xml __pycache__ *.vcd
