################################################################################
# TPU FPGA Build Orchestrator (no nested make)
#
# Usage:
#   make all TARGET=ultra96-v2
#   make tensorcore-ip
#   make tpu-ip TARGET=ultra96-v2
#   make bitstream TARGET=ultra96-v2
################################################################################

TARGET ?= ultra96-v2
TARGETS := ultra96-v2 alveo-u280 alveo-v80
SUPPORTED_TARGETS := ultra96-v2

TENSORCORE_DIR := tensorcore
ULTRA96_DIR := ultra96-v2
ULTRA96_FPGA_RTL_DIR := $(ULTRA96_DIR)/rtl
ULTRA96_IP_REPO_DIR := $(ULTRA96_DIR)/ip_repo
ULTRA96_OUTPUT_DIR := $(ULTRA96_DIR)/output
ULTRA96_PACKAGE_SCRIPT := $(ULTRA96_DIR)/package_tpu_ip.tcl
ULTRA96_BUILD_SCRIPT := $(ULTRA96_DIR)/build_bd_bitstream.tcl

COMPUTE_TILE_DIR := src/compute_tile
ULTRA96_L2_TILE_DIR := src/l2_tile
ULTRA96_SYSTEM_DIR := src/system

# Common FPGA settings (override as needed)
PART ?= xczu3eg-sbva484-1-i
IP_NAME ?= cornell_tpu
IP_VERSION ?= 1.0
IP_VENDOR ?= cornell.edu
IP_LIBRARY ?= user
PROJ_NAME ?= tpu_system
BD_NAME ?= minitpu

# Vivado settings
VIVADO_SETTINGS ?= /opt/xilinx/Vitis/2023.2/settings64.sh
VIVADO ?= vivado
VIVADO_OPTS ?= -mode batch -nojournal
VIVADO_ENV_HINT ?= "source $(VIVADO_SETTINGS)"

# Board settings (default to Ultra96-V2)
BOARD_IP ?= 132.236.59.68
BOARD_USER ?= xilinx
BOARD_PASS ?= xilinx
DEPLOY_DIR ?= /home/xilinx/minitpu_deploy
PROJECT_ROOT ?= $(shell pwd)
ROOT ?= $(PROJECT_ROOT)
VIVADO_CHECK = command -v $(VIVADO) >/dev/null 2>&1 || \
	{ echo "Vivado not found on PATH. Run: $(VIVADO_ENV_HINT)"; exit 2; }
# VIVADO_RUN: Use with additional arguments, e.g., $(call VIVADO_RUN,-source script.tcl)
define VIVADO_RUN
	bash -c "source $(VIVADO_SETTINGS) && vivado $(VIVADO_OPTS) $(1)"
endef

# TensorCore IP packaging
TENSORCORE_IP_REPO ?= $(TENSORCORE_DIR)/ip_repo
TENSORCORE_IP_XML := $(TENSORCORE_IP_REPO)/tensorcore_1.0/component.xml

ULTRA96_IP_OUT_DIR := $(ULTRA96_IP_REPO_DIR)/$(IP_NAME)_$(IP_VERSION)
ULTRA96_COMPONENT_XML := $(ULTRA96_IP_OUT_DIR)/component.xml
ULTRA96_ARTIFACTS_DIR := $(ULTRA96_OUTPUT_DIR)/artifacts
ULTRA96_BITSTREAM := $(ULTRA96_ARTIFACTS_DIR)/$(BD_NAME).bit
ULTRA96_HWH := $(ULTRA96_ARTIFACTS_DIR)/$(BD_NAME).hwh

ifeq ($(TARGET),ultra96-v2)
ULTRA96_IP_DEPS := _ultra96_package_ip
ULTRA96_BIT_DEPS := _ultra96_bitstream
else
ULTRA96_IP_DEPS :=
ULTRA96_BIT_DEPS :=
endif

.PHONY: all help list-targets tensorcore-ip compute_tile-ip tpu-ip bitstream tpu clean \
	clean-tensorcore clean-compute_tile clean-target mem-ip mem-bitstream mem-board-tests

all: bitstream

help:
	@echo "TPU FPGA Build Orchestrator (no nested make)"
	@echo ""
	@echo "Targets:"
	@echo "  tensorcore-ip  Package TensorCore IP (tpu/TensorCore)"
	@echo "  tpu-ip         Package TPU IP for TARGET"
	@echo "  bitstream      Build TPU bitstream for TARGET"
	@echo "  clean          Clean TensorCore + TARGET outputs"
	@echo "  list-targets   Show supported targets"
	@echo ""
	@echo "Targets available: $(TARGETS)"
	@echo "Supported today:   $(SUPPORTED_TARGETS)"
	@echo ""
	@echo "Examples:"
	@echo "  make tensorcore-ip"
	@echo "  make tpu-ip TARGET=ultra96-v2"
	@echo "  make bitstream TARGET=ultra96-v2"
	@echo ""
	@echo "Notes:"
	@echo "  - For Vivado: source /opt/xilinx/Vitis/2023.2/settings64.sh"

list-targets:
	@echo "Targets: $(TARGETS)"
	@echo "Supported today: $(SUPPORTED_TARGETS)"

# -----------------------------------------------------------------------------
# TensorCore IP
# -----------------------------------------------------------------------------

tensorcore-ip: $(TENSORCORE_IP_XML)

$(TENSORCORE_IP_XML): $(TENSORCORE_DIR)/*.sv $(TENSORCORE_DIR)/package_ip.tcl
	@echo "Packaging TensorCore IP..."
	$(call VIVADO_RUN,-source $(TENSORCORE_DIR)/package_ip.tcl -tclargs \
		-part $(PART) -out $(TENSORCORE_IP_REPO) -ip_name tensorcore -ip_version 1.0)

clean-tensorcore:
	rm -rf $(TENSORCORE_IP_REPO) $(TENSORCORE_DIR)/pkg_*_tmp $(TENSORCORE_DIR)/.Xil \
		$(TENSORCORE_DIR)/*.log $(TENSORCORE_DIR)/*.jou

# -----------------------------------------------------------------------------
# TPU IP + Bitstream
# -----------------------------------------------------------------------------

tpu-ip: tensorcore-ip $(ULTRA96_IP_DEPS)
	@if [ "$(TARGET)" != "ultra96-v2" ]; then \
		echo "TARGET=$(TARGET) is not supported yet."; \
		exit 2; \
	fi

bitstream: tpu-ip $(ULTRA96_BIT_DEPS)
	@if [ "$(TARGET)" != "ultra96-v2" ]; then \
		echo "TARGET=$(TARGET) is not supported yet."; \
		exit 2; \
	fi

_ultra96_package_ip: $(ULTRA96_COMPONENT_XML)

$(ULTRA96_COMPONENT_XML): $(TENSORCORE_DIR)/*.sv $(ULTRA96_FPGA_RTL_DIR)/*.v $(ULTRA96_FPGA_RTL_DIR)/*.sv src/system/*.v src/system/*.sv src/compute_tile/*.sv src/l2_tile/*.sv
	@echo "=========================================="
	@echo "Packaging TPU IP: $(IP_NAME) v$(IP_VERSION)"
	@echo "=========================================="
	@mkdir -p $(ULTRA96_IP_REPO_DIR)
	$(call VIVADO_RUN,-source $(ULTRA96_PACKAGE_SCRIPT) -tclargs \
		-ip_name $(IP_NAME) \
		-ip_version $(IP_VERSION) \
		-ip_vendor $(IP_VENDOR) \
		-ip_library $(IP_LIBRARY) \
		-part $(PART) \
		-rtl_dir $(TENSORCORE_DIR) \
		-rtl_dir $(ULTRA96_FPGA_RTL_DIR) \
		-rtl_dir src/system \
		-rtl_dir src/compute_tile \
		-rtl_dir src/l2_tile \
		-repo_out $(ULTRA96_IP_REPO_DIR))
	@echo ""
	@echo "IP packaged successfully: $(ULTRA96_IP_OUT_DIR)"
	@echo ""

_ultra96_bitstream: $(ULTRA96_BITSTREAM)

$(ULTRA96_BITSTREAM): $(ULTRA96_COMPONENT_XML)
	@echo "=========================================="
	@echo "Building Block Design and Bitstream"
	@echo "=========================================="
	@mkdir -p $(ULTRA96_OUTPUT_DIR)
	$(call VIVADO_RUN,-source $(ULTRA96_BUILD_SCRIPT) -tclargs \
		-proj_name $(PROJ_NAME) \
		-part $(PART) \
		-ip_repo_path $(ULTRA96_IP_REPO_DIR) \
		-out_dir $(ULTRA96_OUTPUT_DIR) \
		-bd_name $(BD_NAME))
	@echo ""
	@echo "Build complete!"
	@echo "Artifacts: $(ULTRA96_ARTIFACTS_DIR)"
	@ls -la $(ULTRA96_ARTIFACTS_DIR)/
	@echo ""


# -----------------------------------------------------------------------------
# Memory Subsystem IP + Bitstream
# -----------------------------------------------------------------------------
mem-ip: $(COMPUTE_TILE_DIR)/*.sv $(ULTRA96_SYSTEM_DIR)/*.v $(ULTRA96_SYSTEM_DIR)/*.sv $(TENSORCORE_DIR)/*.sv
	@echo "Packaging mem_subsys IP (with compute tile)..."
	@mkdir -p $(ULTRA96_IP_REPO_DIR)
	$(call VIVADO_RUN,-source scripts/package_mem_ip.tcl -tclargs \
		-ip_name mem_subsys -part $(PART) \
		-rtl_dir $(ULTRA96_SYSTEM_DIR) \
		-rtl_dir $(TENSORCORE_DIR) \
		-rtl_dir $(COMPUTE_TILE_DIR) \
		-repo_out $(ULTRA96_IP_REPO_DIR))

mem-bitstream: mem-ip
	@echo "Building mem_subsys Bitstream..."
	@mkdir -p $(ULTRA96_OUTPUT_DIR)
	$(call VIVADO_RUN,-source scripts/build_mem_bitstream.tcl -tclargs \
		-proj_name mem_system -part $(PART) \
		-ip_repo_path $(ULTRA96_IP_REPO_DIR) \
		-out_dir $(ULTRA96_OUTPUT_DIR) \
		-bd_name mem_bd)

#==============================================================================
# LOCAL SIMULATION
#==============================================================================

.PHONY: verify-compute_unit verify-system_bus verify-system_data

verify-compute_unit:
	@$(MAKE) -C verification/compute_tile test_all

verify-system_bus:
	@$(MAKE) board-test \
		PROGRAM_ABSPATH="$(abspath verification/system/diagnose_ip.py)"

verify-system_data:
	@$(MAKE) board-test \
		PROGRAM_ABSPATH="$(abspath verification/system/test_data_integrity.py)"

# Low-level deployment engine.
# 1. Creates a clean staging area locally.
# 2. Bundles the hardware driver (hal), shared contracts (hw_config), and payload.
# 3. Synchronizes via SCP and executes via SSH/SUDO.
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

tpu:
	@if [ ! -f "$(BIT)" ] && [ ! -f "$(ULTRA96_BITSTREAM)" ]; then \
		echo "Error: Bitstream not found. Provide BIT=path/to/bit or build it first."; \
		exit 1; \
	fi
	@LOCAL_BIT="$(if $(BIT),$(BIT),$(ULTRA96_BITSTREAM))"; \
	LOCAL_HWH="$(if $(HWH),$(HWH),$(ULTRA96_HWH))"; \
	$(MAKE) board-test \
		PROGRAM_ABSPATH="$(abspath scripts/program_fpga.py)" \
		EXTRA_FILES="$$LOCAL_BIT $$LOCAL_HWH" \
		PROGRAM_ABSPATH_ARGS="$$(basename $$LOCAL_BIT)"

#==============================================================================
# SMOKE TESTS
#==============================================================================
.PHONY: smoke-sim smoke-sim-full smoke-board board-tests

smoke-sim:
	@bash scripts/smoke_test.sh --sim

smoke-sim-full:
	@bash scripts/smoke_test.sh --sim-full

# Run the offline board test suite (tpu/board_tests/test_board.py).
# Usage: make board-tests [BOARD_TEST_ARGS="--test devmem_rw_small --verbose"]
BOARD_TEST_ARGS ?=
board-tests:
	@set -euo pipefail; \
	require() { command -v "$$1" >/dev/null 2>&1 || { echo "Missing required tool: $$1" >&2; exit 1; }; }; \
	require ssh; require scp; require sshpass; \
	cd "$(PROJECT_ROOT)"; \
	SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"; \
	DEPLOY_TMP="$$(mktemp -d /tmp/tpu_deploy.XXXXXX)"; \
	trap 'rm -rf "$$DEPLOY_TMP"' EXIT; \
	mkdir -p "$$DEPLOY_TMP/runtime" "$$DEPLOY_TMP/board_tests"; \
	cp -r runtime/. "$$DEPLOY_TMP/runtime/"; \
	cp -r tpu/board_tests/. "$$DEPLOY_TMP/board_tests/"; \
	if [[ -f "$(abspath $(ULTRA96_BITSTREAM))" ]]; then cp "$(abspath $(ULTRA96_BITSTREAM))" "$$DEPLOY_TMP/"; fi; \
	if [[ -f "$(abspath $(ULTRA96_HWH))" ]]; then cp "$(abspath $(ULTRA96_HWH))" "$$DEPLOY_TMP/"; fi; \
	find "$$DEPLOY_TMP" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true; \
	find "$$DEPLOY_TMP" -name '*.pyc' -delete 2>/dev/null || true; \
	if [[ -f "$(ROOT)/hw_config.json" ]]; then cp "$(ROOT)/hw_config.json" "$$DEPLOY_TMP/"; fi; \
	sshpass -p "$(BOARD_PASS)" ssh $$SSH_OPTS "$(BOARD_USER)@$(BOARD_IP)" "mkdir -p $(DEPLOY_DIR)"; \
	sshpass -p "$(BOARD_PASS)" scp -r $$SSH_OPTS "$$DEPLOY_TMP"/* "$(BOARD_USER)@$(BOARD_IP):$(DEPLOY_DIR)/"; \
	echo "== Running board_tests/test_board.py on board =="; \
	sshpass -p "$(BOARD_PASS)" ssh -t $$SSH_OPTS "$(BOARD_USER)@$(BOARD_IP)" \
	"cd $(DEPLOY_DIR) && echo $(BOARD_PASS) | sudo -S python3 board_tests/test_board.py $(BOARD_TEST_ARGS)"

mem-board-tests:
	@$(MAKE) board-test \
		PROGRAM_ABSPATH="$(abspath board_tests/test_mem_system.py)" \
		EXTRA_FILES="$(ULTRA96_OUTPUT_DIR)/artifacts/mem_bd.bit $(ULTRA96_OUTPUT_DIR)/artifacts/mem_bd.hwh" \
		PROGRAM_ABSPATH_ARGS="--bitstream mem_bd.bit $(BOARD_TEST_ARGS)"

clean: clean-compute_tile clean-tensorcore
	@if [ "$(TARGET)" = "ultra96-v2" ]; then \
		rm -rf $(ULTRA96_IP_REPO_DIR) $(ULTRA96_OUTPUT_DIR) $(ULTRA96_DIR)/.Xil \
			$(ULTRA96_DIR)/*.log $(ULTRA96_DIR)/*.jou $(ULTRA96_DIR)/pkg_*_proj; \
	else \
		echo "TARGET=$(TARGET) is not supported yet."; \
	fi

	
concurrency-test:
	@$(MAKE) board-test \
		PROGRAM_ABSPATH="$(abspath board_tests/test_concurrency.py)" \
		EXTRA_FILES="$(ULTRA96_OUTPUT_DIR)/artifacts/mem_bd.bit $(ULTRA96_OUTPUT_DIR)/artifacts/mem_bd.hwh" \
		PROGRAM_ABSPATH_ARGS="--bitstream mem_bd.bit $(BOARD_TEST_ARGS)"
