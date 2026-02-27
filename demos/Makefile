# Mini-TPU Test Suite Orchestrator
#
# This Makefile manages the workflow of using the physical Mini-TPU via Remote Execution.
#
# Environment Setup:
#   export MINITPU_HOST=132.236.59.64  # Set your board IP
#
# Workflow: 
#   1. Compile offline  -> make compile-tests
#   2. Execute against remote board -> make board-comprehensive
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

.PHONY: help all compile-tests clean board-comprehensive board-edge-cases board-pressure start-rpc

# Default target
help: ## Show this help message
	@echo -e "$(GREEN)Mini-TPU Workflow Orchestrator$(RESET)"
	@echo -e "Usage: make $(CYAN)<target>$(RESET)"
	@echo -e ""
	@echo -e "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-25s$(RESET) %s\n", $$1, $$2}'

#==============================================================================
# 1. ARTIFACT GENERATION (Offline Compilation)
#==============================================================================

all: compile-tests

compile-tests: ## Compile all test programs into .tpu_bin offline
	@echo "Compiling comprehensive test..."
	@PYTHONPATH=$(PYTHONPATH) python3 $(PROJECT_ROOT)/compiler/compile.py kernels/comprehensive.tu binaries/comprehensive.tpu_bin
	@echo "Compiling SIMD edge cases..."
	@PYTHONPATH=$(PYTHONPATH) python3 $(PROJECT_ROOT)/compiler/compile.py kernels/simd_edge_cases.tu binaries/simd_edge_cases.tpu_bin
	@echo "Compiling SIMD pressure tests..."
	@PYTHONPATH=$(PYTHONPATH) python3 $(PROJECT_ROOT)/compiler/compile.py kernels/pressure_scalar.tu binaries/pressure_scalar.tpu_bin
	@PYTHONPATH=$(PYTHONPATH) python3 $(PROJECT_ROOT)/compiler/compile.py kernels/pressure_simd.tu binaries/pressure_simd.tpu_bin
	@echo -e "$(GREEN)All artifacts ready in binaries/$(RESET)"

#==============================================================================
# 2. BOARD EXECUTION (Local Execution over RPC or Simulator Mode)
#==============================================================================

board-comprehensive: ## Run full functional suite on board
	@PYTHONPATH=$(PYTHONPATH) python3 programs/comprehensive_test.tu

board-edge-cases: ## Run SIMD corner-case tests on board
	@PYTHONPATH=$(PYTHONPATH) python3 programs/simd_edge_cases_test.tu

board-pressure: ## Run performance stress tests on board
	@PYTHONPATH=$(PYTHONPATH) python3 programs/simd_pressure_test.tu --mode both

start-rpc: deploy-runtime ## Start the RPC server on the remote board via SSH
	@echo -e "$(GREEN)== Starting RPC server on board ==$(RESET)"
	@sshpass -p "$(BOARD_PASS)" ssh -t -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$(BOARD_USER)@$(BOARD_IP)" \
	"cd $(DEPLOY_DIR) && echo $(BOARD_PASS) | sudo -S env PYTHONPATH=. python3 runtime/rpc_server.py"

deploy-runtime: ## Deploy the runtime python files to the board
	@echo -e "$(GREEN)== Deploying runtime to board ==$(RESET)"
	@sshpass -p "$(BOARD_PASS)" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$(BOARD_USER)@$(BOARD_IP)" "mkdir -p $(DEPLOY_DIR)/runtime"
	@sshpass -p "$(BOARD_PASS)" scp -r -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null $(PROJECT_ROOT)/runtime/* "$(BOARD_USER)@$(BOARD_IP):$(DEPLOY_DIR)/runtime/"

#==============================================================================
# 3. UTILITIES
#==============================================================================

clean: ## Remove generated binaries and temporary files
	rm -rf binaries/*.npz binaries/*.tpubin binaries/*.tpu_bin tuda_result.txt
	@echo "Cleaned."
