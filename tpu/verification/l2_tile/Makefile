# Makefile for L2 Tile RTL Tests
IVERILOG = iverilog
VVP = vvp
COCOTB_LIBS = $(shell python3 -c "import cocotb; import os; print(os.path.join(os.path.dirname(cocotb.__file__), 'libs'))")

SIM_BUILD = sim_build
WAVEFORMS = waveforms

export COCOTB_REDUCED_LOG_FMT = 1
export PYTHONPATH := $(PWD):$(PYTHONPATH)
export PYGPI_PYTHON_BIN = $(shell python3 -c "import sys; print(sys.executable)")

IVFLAGS = -g2012 -Wall

# L2 tile RTL sources (l2_tile + tma_engine + L2 SRAM behavioral model)
SRC_L2 = ../../src/l2_tile/l2_tile.sv \
         ../../src/l2_tile/tma_engine.sv \
         ../compute_tile/wrappers/blk_mem_models.sv

test_tma: $(SIM_BUILD)
	@echo "=== Running TMA Engine Tests ==="
	$(IVERILOG) -o $(SIM_BUILD)/sim.vvp -s l2_tile $(IVFLAGS) $(SRC_L2)
	MODULE=test_tma COCOTB_TEST_MODULES=test_tma $(VVP) -M $(COCOTB_LIBS) -m libcocotbvpi_icarus $(SIM_BUILD)/sim.vvp
	@! grep -q '<failure\|<error' results.xml || (echo "TEST FAILED" && exit 1)
	@echo "=== TMA Engine Tests Complete ==="

$(SIM_BUILD):
	mkdir -p $(SIM_BUILD)
	mkdir -p $(WAVEFORMS)

clean:
	rm -rf $(SIM_BUILD) $(WAVEFORMS)/*.vcd results.xml __pycache__ *.vcd

.PHONY: test_tma clean
