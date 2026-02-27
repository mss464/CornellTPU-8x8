# Makefile for L2 Tile RTL Tests
IVERILOG = iverilog
VVP = vvp

# Prefer the minitpu conda environment Python (has cocotbext-axi).
CONDA_PYTHON := $(shell conda run -n minitpu which python3 2>/dev/null || which python3)
COCOTB_LIBS := $(shell $(CONDA_PYTHON) -c "import cocotb; import os; print(os.path.join(os.path.dirname(cocotb.__file__), 'libs'))")

SIM_BUILD = sim_build
WAVEFORMS = waveforms

CONDA_SITE_PKGS := $(shell $(CONDA_PYTHON) -c "import site; print(':'.join(site.getsitepackages()))" 2>/dev/null)

export COCOTB_REDUCED_LOG_FMT = 1
export PYTHONPATH := $(PWD):$(CONDA_SITE_PKGS):$(PYTHONPATH)
export PYGPI_PYTHON_BIN = $(CONDA_PYTHON)

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

all: test_tma

$(SIM_BUILD):
	mkdir -p $(SIM_BUILD)
	mkdir -p $(WAVEFORMS)

clean:
	rm -rf $(SIM_BUILD) $(WAVEFORMS)/*.vcd results.xml __pycache__ *.vcd

help:
	@echo "L2 Tile RTL Test Makefile"
	@echo ""
	@echo "  make test_tma   - TMA engine transfer tests"
	@echo "  make all        - Run all L2 tile tests"
	@echo "  make clean      - Remove build artifacts"

.PHONY: test_tma all clean help
