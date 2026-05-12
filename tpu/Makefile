# Optimized memory subsystem build and board-test targets.

PART ?= xczu3eg-sbva484-1-i
VIVADO_SETTINGS ?= /opt/xilinx/Vitis/2023.2/settings64.sh
VIVADO ?= vivado
VIVADO_OPTS ?= -mode batch -nojournal

TENSORCORE_DIR := tensorcore
COMPUTE_TILE_DIR := src/compute_tile
SYSTEM_DIR := src/system
SCRIPTS_DIR := scripts

ULTRA96_DIR := ultra96-v2
ULTRA96_IP_REPO_DIR := $(ULTRA96_DIR)/ip_repo
ULTRA96_OUTPUT_DIR := $(ULTRA96_DIR)/output
ULTRA96_ARTIFACTS_DIR := $(ULTRA96_OUTPUT_DIR)/artifacts
ULTRA96_BITSTREAM := $(ULTRA96_ARTIFACTS_DIR)/mem_bd.bit
ULTRA96_HWH := $(ULTRA96_ARTIFACTS_DIR)/mem_bd.hwh

BOARD_IP ?= 132.236.59.68
BOARD_USER ?= xilinx
BOARD_PASS ?= xilinx
DEPLOY_DIR ?= /home/xilinx/minitpu_deploy
PROJECT_ROOT ?= $(shell pwd)
ROOT ?= $(PROJECT_ROOT)
BOARD_TEST_ARGS ?=
BENCH_ARGS ?=

define VIVADO_RUN
	bash -c "source $(VIVADO_SETTINGS) && $(VIVADO) $(VIVADO_OPTS) $(1)"
endef

.PHONY: all help mem-ip mem-bitstream board-test mem-board-tests concurrency-test \
	mem-benchmark benchmark clean

all: mem-bitstream

help:
	@echo "Optimized memory subsystem targets"
	@echo ""
	@echo "Build:"
	@echo "  make mem-ip            Package mem_subsys IP"
	@echo "  make mem-bitstream     Build Ultra96-v2 mem_bd.bit/mem_bd.hwh"
	@echo "  make clean             Remove generated Vivado artifacts"
	@echo ""
	@echo "Board:"
	@echo "  make mem-board-tests BOARD_IP=<ip>"
	@echo "  make concurrency-test BOARD_IP=<ip>"
	@echo "  make mem-benchmark BOARD_IP=<ip> BENCH_ARGS=\"--repeats 5 --warmups 1\""

mem-ip: $(SCRIPTS_DIR)/package_mem_ip.tcl $(SYSTEM_DIR)/*.v $(SYSTEM_DIR)/*.sv \
		$(TENSORCORE_DIR)/*.sv $(COMPUTE_TILE_DIR)/*.sv
	@echo "Packaging mem_subsys IP..."
	@mkdir -p $(ULTRA96_IP_REPO_DIR)
	$(call VIVADO_RUN,-source $(SCRIPTS_DIR)/package_mem_ip.tcl -tclargs \
		-ip_name mem_subsys \
		-part $(PART) \
		-rtl_dir $(SYSTEM_DIR) \
		-rtl_dir $(TENSORCORE_DIR) \
		-rtl_dir $(COMPUTE_TILE_DIR) \
		-repo_out $(ULTRA96_IP_REPO_DIR))

mem-bitstream: mem-ip $(SCRIPTS_DIR)/build_mem_bitstream.tcl
	@echo "Building optimized memory subsystem bitstream..."
	@mkdir -p $(ULTRA96_OUTPUT_DIR)
	$(call VIVADO_RUN,-source $(SCRIPTS_DIR)/build_mem_bitstream.tcl -tclargs \
		-proj_name mem_system \
		-part $(PART) \
		-ip_repo_path $(ULTRA96_IP_REPO_DIR) \
		-out_dir $(ULTRA96_OUTPUT_DIR) \
		-bd_name mem_bd)
	@echo "Artifacts:"
	@ls -la $(ULTRA96_ARTIFACTS_DIR)

# Low-level deployment engine used by board tests and benchmarks.
board-test:
	@set -euo pipefail; \
	require() { command -v "$$1" >/dev/null 2>&1 || { echo "Missing required tool: $$1" >&2; exit 1; }; }; \
	require ssh; require scp; require sshpass; \
	cd "$(PROJECT_ROOT)"; \
	if [[ ! -f "$(PROGRAM_ABSPATH)" ]]; then \
		echo "Missing test program: $(PROGRAM_ABSPATH)" >&2; \
		exit 1; \
	fi; \
	SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"; \
	DEPLOY_TMP="$$(mktemp -d /tmp/tpu_deploy.XXXXXX)"; \
	trap 'rm -rf "$$DEPLOY_TMP"' EXIT; \
	mkdir -p "$$DEPLOY_TMP/runtime"; \
	cp -r runtime/. "$$DEPLOY_TMP/runtime/"; \
	PROGRAM_RELPATH="$$(python3 -c "import os; p=os.path.relpath('$(PROGRAM_ABSPATH)','$(PROJECT_ROOT)'); print('' if p.startswith('..') else p)")"; \
	if [[ -z "$$PROGRAM_RELPATH" || ! -f "$$DEPLOY_TMP/$$PROGRAM_RELPATH" ]]; then \
		cp "$(PROGRAM_ABSPATH)" "$$DEPLOY_TMP/"; \
		PROGRAM_RELPATH="$$(basename "$(PROGRAM_ABSPATH)")"; \
	fi; \
	if [[ -f "$(ROOT)/hw_config.json" ]]; then cp "$(ROOT)/hw_config.json" "$$DEPLOY_TMP/"; fi; \
	for extra in $(EXTRA_FILES); do \
		if [[ -f "$$extra" ]]; then cp "$$extra" "$$DEPLOY_TMP/"; fi; \
	done; \
	find "$$DEPLOY_TMP" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true; \
	find "$$DEPLOY_TMP" -name "*.pyc" -delete 2>/dev/null || true; \
	sshpass -p "$(BOARD_PASS)" ssh $$SSH_OPTS "$(BOARD_USER)@$(BOARD_IP)" "mkdir -p $(DEPLOY_DIR)"; \
	sshpass -p "$(BOARD_PASS)" scp -r $$SSH_OPTS "$$DEPLOY_TMP"/* "$(BOARD_USER)@$(BOARD_IP):$(DEPLOY_DIR)/"; \
	echo "== Running $$PROGRAM_RELPATH on board =="; \
	sshpass -p "$(BOARD_PASS)" ssh -t $$SSH_OPTS "$(BOARD_USER)@$(BOARD_IP)" \
	"cd $(DEPLOY_DIR) && echo $(BOARD_PASS) | sudo -S python3 $$PROGRAM_RELPATH $(PROGRAM_ABSPATH_ARGS)"

mem-board-tests:
	@$(MAKE) board-test \
		PROGRAM_ABSPATH="$(abspath board_tests/test_mem_system.py)" \
		EXTRA_FILES="$(ULTRA96_BITSTREAM) $(ULTRA96_HWH)" \
		PROGRAM_ABSPATH_ARGS="--bitstream mem_bd.bit --program --latency 0 $(BOARD_TEST_ARGS)"

concurrency-test:
	@$(MAKE) board-test \
		PROGRAM_ABSPATH="$(abspath board_tests/test_concurrency.py)" \
		EXTRA_FILES="$(ULTRA96_BITSTREAM) $(ULTRA96_HWH)" \
		PROGRAM_ABSPATH_ARGS="--bitstream mem_bd.bit --program --latency 0 $(BOARD_TEST_ARGS)"

mem-benchmark:
	@$(MAKE) board-test \
		PROGRAM_ABSPATH="$(abspath benchmarks/mem_benchmark.py)" \
		EXTRA_FILES="$(ULTRA96_BITSTREAM) $(ULTRA96_HWH)" \
		PROGRAM_ABSPATH_ARGS="--bitstream mem_bd.bit --program --latency 0 $(BENCH_ARGS)"

benchmark: mem-benchmark

clean:
	rm -rf $(ULTRA96_IP_REPO_DIR) $(ULTRA96_OUTPUT_DIR) $(ULTRA96_DIR)/.Xil \
		build .Xil vivado*.log vivado*.jou *.log *.jou
