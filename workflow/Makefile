# Mini-TPU Test Suite Orchestrator
#
# This Makefile manages the lifecycle of testing the Mini-TPU across different 
# environments: LOCAL (Simulation) and BOARD (Physical FPGA).
#
# Environment Setup:
#   export BOARD_IP=132.236.59.64  # Set your board IP
#
# Workflow:
#   1. (Hardware) Build & Program -> make -C .. fpga
#   2. (Software) Compile kernels -> make compile-tests
#   3. (Execution) Run on Board   -> make board-comprehensive
#
#

PROJECT_ROOT := $(abspath $(CURDIR)/..)
ROOT         := $(PROJECT_ROOT)/tpu
SHELL        := /usr/bin/env bash
PYTHONPATH   := $(PROJECT_ROOT):$(ROOT):$(CURDIR)

# Board Credentials & Paths
BOARD_USER   ?= xilinx
BOARD_IP     ?= 132.236.59.64
BOARD_PASS   ?= xilinx
DEPLOY_DIR   ?= ~/tpu_deploy

.PHONY: help board-test board-comprehensive board-simd board-edge-cases board-pressure board-data-integrity

#==============================================================================
# 1. ARTIFACT GENERATION
#==============================================================================

# Compile individual test programs from their python sources in programs/
.PHONY: compile-tests
compile-tests:
	@echo "Recompiling all test artifacts..."
	@PYTHONPATH=$(PYTHONPATH) python3 tools/harness.py programs/comprehensive.py
	@PYTHONPATH=$(PYTHONPATH) python3 tools/harness.py programs/simd_comparison.py
	@PYTHONPATH=$(PYTHONPATH) python3 tools/harness.py programs/simd_edge_cases.py
	@PYTHONPATH=$(PYTHONPATH) python3 tools/harness.py programs/simd_pressure.py

# Usage: make executable PY=programs/comprehensive.py [OUT=binaries/comprehensive.npz]
.PHONY: executable
executable:
	@PYTHONPATH=$(PYTHONPATH) python3 tools/harness.py $(PY) $(if $(OUT),-o $(OUT),)

#==============================================================================
# 2. BOARD EXECUTION (Real Hardware)
#==============================================================================

# Low-level deployment engine.
# 1. Creates a clean staging area locally.
# 2. Bundles the hardware driver (hal), shared contracts (hw_config), and payload.
# 3. Synchronizes via SCP and executes via SSH/SUDO.
# Generic test launcher deployment
# Usage: make tpu_go_brrr EXE=path/to/test.npz
.PHONY: tpu_go_brrr
tpu_go_brrr:
	@set -euo pipefail; \
	require() { command -v "$$1" >/dev/null 2>&1 || { echo "Missing required tool: $$1" >&2; exit 1; }; }; \
	require ssh; require scp; require sshpass; \
	cd "$(PROJECT_ROOT)"; \
	EXE_PATH="$(EXE)"; \
	if [[ ! -f "$$EXE_PATH" ]]; then \
		echo "Missing test executable: $$EXE_PATH" >&2; \
		exit 1; \
	fi; \
	SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"; \
	DEPLOY_TMP="$$(mktemp -d /tmp/tpu_deploy.XXXXXX)"; \
	trap 'rm -rf "$$DEPLOY_TMP"' EXIT; \
	mkdir -p "$$DEPLOY_TMP/compiler/hal"; \
	cp compiler/hal/pynq_host.py "$$DEPLOY_TMP/compiler/hal/"; \
	touch "$$DEPLOY_TMP/compiler/__init__.py" "$$DEPLOY_TMP/compiler/hal/__init__.py"; \
	cp workflow/tools/test_launcher.py "$$DEPLOY_TMP/"; \
	cp "$$EXE_PATH" "$$DEPLOY_TMP/"; \
	EXE_NAME="$$(basename "$$EXE_PATH")"; \
	if [[ -f "$(ROOT)/hw_config.json" ]]; then cp "$(ROOT)/hw_config.json" "$$DEPLOY_TMP/"; fi; \
	echo "== Deploying $$EXE_NAME to board =="; \
	sshpass -p "$(BOARD_PASS)" ssh $$SSH_OPTS "$(BOARD_USER)@$(BOARD_IP)" "mkdir -p $(DEPLOY_DIR)"; \
	sshpass -p "$(BOARD_PASS)" scp -r $$SSH_OPTS "$$DEPLOY_TMP"/* "$(BOARD_USER)@$(BOARD_IP):$(DEPLOY_DIR)/"; \
	echo "== Running test_launcher.py with $$EXE_NAME =="; \
	sshpass -p "$(BOARD_PASS)" ssh -t $$SSH_OPTS "$(BOARD_USER)@$(BOARD_IP)" \
	"cd $(DEPLOY_DIR) && echo $(BOARD_PASS) | sudo -S python3 test_launcher.py $$EXE_NAME"

board-comprehensive:
	@PYTHONPATH=$(PYTHONPATH) python3 tools/harness.py programs/comprehensive.py
	@$(MAKE) --no-print-directory tpu_go_brrr \
		EXE="workflow/binaries/comprehensive.npz"

board-simd:
	@PYTHONPATH=$(PYTHONPATH) python3 tools/harness.py programs/simd_comparison.py
	@$(MAKE) --no-print-directory tpu_go_brrr \
		EXE="workflow/binaries/simd_comparison.npz"

board-edge-cases:
	@PYTHONPATH=$(PYTHONPATH) python3 tools/harness.py programs/simd_edge_cases.py
	@$(MAKE) --no-print-directory tpu_go_brrr \
		EXE="workflow/binaries/simd_edge_cases.npz"

board-pressure:
	@PYTHONPATH=$(PYTHONPATH) python3 tools/harness.py programs/simd_pressure.py
	@echo "--- Running Scalar Pressure Test ---"
	@$(MAKE) --no-print-directory tpu_go_brrr \
		EXE="workflow/binaries/pressure_scalar.npz"
	@echo "--- Running SIMD Pressure Test ---"
	@$(MAKE) --no-print-directory tpu_go_brrr \
		EXE="workflow/binaries/pressure_simd.npz"


#==============================================================================
# 4. UTILITIES
#==============================================================================

help:
	@echo "Mini-TPU Test Suite"
	@echo "--------------------"
	@echo "Board Targets (Real HW):"
	@echo "  make board-comprehensive  - Run full edge-case functional suite"
	@echo "  make board-simd           - Compare Scalar vs SIMD VPU results"
	@echo "  make board-edge-cases     - Run SIMD corner-case tests"
	@echo "  make board-pressure       - Run performance/timing stress tests"
	@echo "  make board-data-integrity - Verify BRAM access (no compute)"
	@echo ""
	@echo ""
	@echo "Management:"
	@echo "  make executable-all       - Re-generate all instruction artifacts"
	@echo "  make help                 - Show this message"
