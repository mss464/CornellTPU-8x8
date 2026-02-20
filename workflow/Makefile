# Mini-TPU Test Suite Orchestrator
#
# This Makefile manages the workflow of using the physical Mini-TPU on a board.
# PLANNED: Add simulation support.
#
# Environment Setup:
#   export BOARD_IP=132.236.59.64  # Set your board IP
#   export BOARD_PASS=xilinx       # Set your board password
#   export BOARD_USER=xilinx       # Set your board username
#
# Workflow (assumes the TPU is already prepared on FPGA): 
#   1. (Software) Compile kernels -> make compile-tests
#   2. (Execution) Run on Board   -> make board-comprehensive
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

# Aesthetics
CYAN  := \033[36m
GREEN := \033[32m
RESET := \033[0m

.PHONY: help all compile-tests clean board-comprehensive board-simd board-edge-cases board-pressure

# Default target
help: ## Show this help message
	@echo -e "$(GREEN)Mini-TPU Workflow Orchestrator$(RESET)"
	@echo -e "Usage: make $(CYAN)<target>$(RESET)"
	@echo -e ""
	@echo -e "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-25s$(RESET) %s\n", $$1, $$2}'

#==============================================================================
# 1. ARTIFACT GENERATION
#==============================================================================

all: compile-tests ## Compile all test programs

compile-tests: binaries/comprehensive.npz binaries/simd_comparison.npz binaries/simd_edge_cases.npz binaries/pressure_scalar.npz ## Recompile all test artifacts
	@echo -e "$(GREEN)All artifacts ready in binaries/$(RESET)"

# Pattern rule for single-executable programs
binaries/%.npz: programs/%.py
	@mkdir -p binaries
	@echo "Compiling $<..."
	@PYTHONPATH=$(PYTHONPATH) python3 tools/harness.py $< -o $@

# Special case for simd_pressure which generates two files
binaries/pressure_scalar.npz binaries/pressure_simd.npz: programs/simd_pressure.py
	@mkdir -p binaries
	@echo "Compiling pressure tests from $<..."
	@PYTHONPATH=$(PYTHONPATH) python3 tools/harness.py $< -o binaries/

#==============================================================================
# 2. BOARD EXECUTION (Real Hardware)
#==============================================================================

board-comprehensive: binaries/comprehensive.npz ## Run full functional suite on board
	@$(MAKE) --no-print-directory tpu_go_brrr EXE=$<

board-simd: binaries/simd_comparison.npz ## Compare Scalar vs SIMD VPU on board
	@$(MAKE) --no-print-directory tpu_go_brrr EXE=$<

board-edge-cases: binaries/simd_edge_cases.npz ## Run SIMD corner-case tests on board
	@$(MAKE) --no-print-directory tpu_go_brrr EXE=$<

board-pressure: binaries/pressure_scalar.npz binaries/pressure_simd.npz ## Run performance stress tests on board
	@echo "--- Running Scalar Pressure Test ---"
	@$(MAKE) --no-print-directory tpu_go_brrr EXE=binaries/pressure_scalar.npz
	@echo "--- Running SIMD Pressure Test ---"
	@$(MAKE) --no-print-directory tpu_go_brrr EXE=binaries/pressure_simd.npz

# Low-level deployment engine.
# 1. Creates a clean staging area locally.
# 2. Bundles the hardware driver (runtime), shared contracts (hw_config), and payload.
# 3. Synchronizes via SCP and executes via SSH/SUDO.
# Generic test launcher deployment
# Usage: make tpu_go_brrr EXE=path/to/test.npz
.PHONY: tpu_go_brrr
tpu_go_brrr:
	@set -euo pipefail; \
	require() { command -v "$$1" >/dev/null 2>&1 || { echo "Missing required tool: $$1" >&2; exit 1; }; }; \
	require ssh; require scp; require sshpass; \
	EXE_PATH="$(abspath $(EXE))"; \
	if [[ ! -f "$$EXE_PATH" ]]; then \
		echo "Missing test executable: $$EXE_PATH" >&2; \
		exit 1; \
	fi; \
	SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"; \
	DEPLOY_TMP="$$(mktemp -d /tmp/tpu_deploy.XXXXXX)"; \
	trap 'rm -rf "$$DEPLOY_TMP"' EXIT; \
	mkdir -p "$$DEPLOY_TMP/runtime"; \
	cp "$(PROJECT_ROOT)/runtime/pynq_host.py" "$$DEPLOY_TMP/runtime/"; \
	touch "$$DEPLOY_TMP/runtime/__init__.py"; \
	cp "$(CURDIR)/tools/test_launcher.py" "$$DEPLOY_TMP/"; \
	cp "$$EXE_PATH" "$$DEPLOY_TMP/"; \
	EXE_NAME="$$(basename "$$EXE_PATH")"; \
	if [[ -f "$(ROOT)/hw_config.json" ]]; then cp "$(ROOT)/hw_config.json" "$$DEPLOY_TMP/"; fi; \
	echo -e "$(GREEN)== Deploying $$EXE_NAME to board ($(BOARD_IP)) ==$(RESET)"; \
	sshpass -p "$(BOARD_PASS)" ssh $$SSH_OPTS "$(BOARD_USER)@$(BOARD_IP)" "mkdir -p $(DEPLOY_DIR)"; \
	sshpass -p "$(BOARD_PASS)" scp -r $$SSH_OPTS "$$DEPLOY_TMP"/* "$(BOARD_USER)@$(BOARD_IP):$(DEPLOY_DIR)/"; \
	echo -e "$(GREEN)== Executing $$EXE_NAME ==$(RESET)"; \
	sshpass -p "$(BOARD_PASS)" ssh -t $$SSH_OPTS "$(BOARD_USER)@$(BOARD_IP)" \
	"cd $(DEPLOY_DIR) && echo $(BOARD_PASS) | sudo -S python3 test_launcher.py $$EXE_NAME"

#==============================================================================
# 3. UTILITIES
#==============================================================================

clean: ## Remove generated binaries and temporary files
	rm -rf binaries/*.npz
	@echo "Cleaned."

