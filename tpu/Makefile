################################################################################
# TPU FPGA Build Orchestrator (no nested make)
#
# Usage:
#   make all TARGET=ultra96-v2
#   make compute_tile-ip
#   make tpu-ip TARGET=ultra96-v2
#   make bitstream TARGET=ultra96-v2
################################################################################

TARGET ?= ultra96-v2
TARGETS := ultra96-v2 alveo-u280
SUPPORTED_TARGETS := ultra96-v2

COMPUTE_TILE_DIR := src/compute_tile
ULTRA96_DIR := .
ULTRA96_FPGA_RTL_DIR := src/system
ULTRA96_L2_TILE_DIR := src/l2_tile
ULTRA96_IP_REPO_DIR := ip_repo
ULTRA96_OUTPUT_DIR := build
ULTRA96_PACKAGE_SCRIPT := scripts/package_tpu_ip.tcl
ULTRA96_BUILD_SCRIPT := scripts/build_bd_bitstream.tcl

# Common FPGA settings (override as needed)
PART ?= xczu3eg-sbva484-1-i
IP_NAME ?= minitpu
IP_VERSION ?= 1.0
IP_VENDOR ?= minitpu_team
IP_LIBRARY ?= user
PROJ_NAME ?= minitpu
BD_NAME ?= minitpu

# Board Credentials & Paths
BOARD_USER ?= xilinx
BOARD_IP   ?= 132.236.59.64
BOARD_PASS ?= xilinx
DEPLOY_DIR ?= ~/tpu_deploy
PROJECT_ROOT := $(abspath $(CURDIR)/..)
ROOT         := .

# Vivado settings
VIVADO_SETTINGS ?= /opt/xilinx/Vitis/2023.2/settings64.sh
VIVADO ?= vivado
VIVADO_OPTS ?= -mode batch -nojournal
VIVADO_ENV_HINT ?= "source $(VIVADO_SETTINGS)"
VIVADO_CHECK = command -v $(VIVADO) >/dev/null 2>&1 || \
	{ echo "Vivado not found on PATH. Run: $(VIVADO_ENV_HINT)"; exit 2; }
# VIVADO_RUN: Use with additional arguments, e.g., $(call VIVADO_RUN,-source script.tcl)
define VIVADO_RUN
	bash -c "source $(VIVADO_SETTINGS) && vivado $(VIVADO_OPTS) $(1)"
endef

# compute_tile IP packaging
# compute_tile IP packaging
compute_tile_PACKAGE_SCRIPT := scripts/package_compute_tile_ip.tcl
compute_tile_IP_REPO ?= $(ULTRA96_IP_REPO_DIR)
compute_tile_IP_XML := $(compute_tile_IP_REPO)/compute_tile_1.0/component.xml

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

.PHONY: all help list-targets compute_tile-ip tpu-ip bitstream tpu clean \
	clean-compute_tile clean-target

all: bitstream

help:
	@echo "TPU Hardware Build Orchestrator (no nested make)"
	@echo ""
	@echo "Targets:"
	@echo "  compute_tile-ip  Package compute_tile IP (tpu/compute_tile)"
	@echo "  tpu-ip         Package TPU IP for TARGET"
	@echo "  bitstream      Build TPU bitstream for TARGET"
	@echo "  tpu            Prepare hardware by programming FPGA bitstream to board (requires BIT and HWH)"
	@echo "  clean          Clean compute_tile + TARGET outputs"
	@echo "  list-targets   Show supported targets"
	@echo "  sim-unit       Run RTL unit tests (local simulation)"
	@echo "  sim-all        Run comprehensive RTL verification (local simulation)"
	@echo ""
	@echo "Targets available: $(TARGETS)"
	@echo "Supported today:   $(SUPPORTED_TARGETS)"
	@echo ""
	@echo "Examples:"
	@echo "  make compute_tile-ip"
	@echo "  make tpu-ip TARGET=ultra96-v2"
	@echo "  make bitstream TARGET=ultra96-v2"
	@echo "  make tpu BIT=build/artifacts/minitpu.bit HWH=build/artifacts/minitpu.hwh"
	@echo ""
	@echo "Notes:"
	@echo "  - For Vivado: source /opt/xilinx/Vitis/2023.2/settings64.sh"

list-targets:
	@echo "Targets: $(TARGETS)"
	@echo "Supported today: $(SUPPORTED_TARGETS)"

# -----------------------------------------------------------------------------
# compute_tile IP
# -----------------------------------------------------------------------------

compute_tile-ip: $(compute_tile_IP_XML)

$(compute_tile_IP_XML): $(COMPUTE_TILE_DIR)/*.sv $(compute_tile_PACKAGE_SCRIPT)
	@echo "Packaging compute_tile IP..."
	$(call VIVADO_RUN,-source $(compute_tile_PACKAGE_SCRIPT) -tclargs \
		-part $(PART) -in $(COMPUTE_TILE_DIR) -out $(compute_tile_IP_REPO) -ip_name compute_tile -ip_version 1.0)

clean-compute_tile:
	rm -rf $(compute_tile_IP_REPO)/compute_tile_1.0 $(COMPUTE_TILE_DIR)/pkg_*_tmp $(COMPUTE_TILE_DIR)/.Xil \
		$(COMPUTE_TILE_DIR)/*.log $(COMPUTE_TILE_DIR)/*.jou

# -----------------------------------------------------------------------------
# TPU IP + Bitstream
# -----------------------------------------------------------------------------

tpu-ip: compute_tile-ip $(ULTRA96_IP_DEPS)
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

$(ULTRA96_COMPONENT_XML): $(COMPUTE_TILE_DIR)/*.sv $(ULTRA96_FPGA_RTL_DIR)/*.v $(ULTRA96_FPGA_RTL_DIR)/*.sv $(ULTRA96_L2_TILE_DIR)/*.sv
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
		-rtl_dir $(COMPUTE_TILE_DIR) \
		-rtl_dir $(ULTRA96_FPGA_RTL_DIR) \
		-rtl_dir $(ULTRA96_L2_TILE_DIR) \
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

#==============================================================================
# LOCAL SIMULATION
#==============================================================================

.PHONY: verify-compute_unit verify-system_bus verify-system_data

verify-compute_unit:
	@$(MAKE) -C verification/compute_tile test_all

verify-system_bus:
	@$(MAKE) board-test \
		PROGRAM="$(abspath verification/system/diagnose_ip.py)"

verify-system_data:
	@$(MAKE) board-test \
		PROGRAM="$(abspath verification/system/test_data_integrity.py)"

# Low-level deployment engine.
# 1. Creates a clean staging area locally.
# 2. Bundles the hardware driver (hal), shared contracts (hw_config), and payload.
# 3. Synchronizes via SCP and executes via SSH/SUDO.
board-test:
	@set -euo pipefail; \
	require() { command -v "$$1" >/dev/null 2>&1 || { echo "Missing required tool: $$1" >&2; exit 1; }; }; \
	require ssh; require scp; require sshpass; \
	cd "$(PROJECT_ROOT)"; \
	PROGRAM_PATH="$(PROGRAM)"; \
	if [[ ! -f "$$PROGRAM_PATH" ]]; then \
		echo "Missing test program: $$PROGRAM_PATH" >&2; \
		exit 1; \
	fi; \
	SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"; \
	DEPLOY_TMP="$$(mktemp -d /tmp/tpu_deploy.XXXXXX)"; \
	trap 'rm -rf "$$DEPLOY_TMP"' EXIT; \
	mkdir -p "$$DEPLOY_TMP/runtime"; \
	cp runtime/pynq_host.py "$$DEPLOY_TMP/runtime/"; \
	touch "$$DEPLOY_TMP/runtime/__init__.py"; \
	cp "$$PROGRAM_PATH" "$$DEPLOY_TMP/"; \
	if [[ -f "$(ROOT)/hw_config.json" ]]; then cp "$(ROOT)/hw_config.json" "$$DEPLOY_TMP/"; fi; \
	for extra in $(EXTRA_FILES); do \
		if [[ -f "$$extra" ]]; then cp "$$extra" "$$DEPLOY_TMP/"; fi; \
	done; \
	PROGRAM_NAME="$$(basename "$$PROGRAM_PATH")"; \
	sshpass -p "$(BOARD_PASS)" ssh $$SSH_OPTS "$(BOARD_USER)@$(BOARD_IP)" "mkdir -p $(DEPLOY_DIR)"; \
	sshpass -p "$(BOARD_PASS)" scp -r $$SSH_OPTS "$$DEPLOY_TMP"/* "$(BOARD_USER)@$(BOARD_IP):$(DEPLOY_DIR)/"; \
	echo "== Running $$PROGRAM_NAME on board =="; \
	sshpass -p "$(BOARD_PASS)" ssh -t $$SSH_OPTS "$(BOARD_USER)@$(BOARD_IP)" \
	"cd $(DEPLOY_DIR) && echo $(BOARD_PASS) | sudo -S python3 $$PROGRAM_NAME $(PROGRAM_ARGS)"

tpu:
	@if [ ! -f "$(BIT)" ] && [ ! -f "$(ULTRA96_BITSTREAM)" ]; then \
		echo "Error: Bitstream not found. Provide BIT=path/to/bit or build it first."; \
		exit 1; \
	fi
	@LOCAL_BIT="$(if $(BIT),$(BIT),$(ULTRA96_BITSTREAM))"; \
	LOCAL_HWH="$(if $(HWH),$(HWH),$(ULTRA96_HWH))"; \
	$(MAKE) board-test \
		PROGRAM="$(abspath scripts/program_fpga.py)" \
		EXTRA_FILES="$$LOCAL_BIT $$LOCAL_HWH" \
		PROGRAM_ARGS="$$(basename $$LOCAL_BIT)"

#==============================================================================
# SMOKE TESTS
#==============================================================================
.PHONY: smoke-sim smoke-sim-full smoke-board

smoke-sim:
	@bash scripts/smoke_test.sh --sim

smoke-sim-full:
	@bash scripts/smoke_test.sh --sim-full

smoke-board:
	@$(MAKE) board-test \
		PROGRAM="$(abspath ../demos/programs/smoke_board.tu)"

clean: clean-compute_tile
	@if [ "$(TARGET)" = "ultra96-v2" ]; then \
		rm -rf $(ULTRA96_IP_REPO_DIR) $(ULTRA96_OUTPUT_DIR) $(ULTRA96_DIR)/.Xil \
			$(ULTRA96_DIR)/*.log $(ULTRA96_DIR)/*.jou $(ULTRA96_DIR)/pkg_*_proj; \
	else \
		echo "TARGET=$(TARGET) is not supported yet."; \
	fi
