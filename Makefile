PART ?= xczu3eg-sbva484-1-i
VIVADO_SETTINGS ?= /opt/xilinx/Vitis/2023.2/settings64.sh
VIVADO_OPTS ?= -mode batch -nojournal

BUILD_DIR ?= build
IP_REPO_DIR := $(BUILD_DIR)/ip_repo
ARTIFACTS_DIR := $(BUILD_DIR)/artifacts
DEPLOY_DIR := compiler/tpu_deploy

RTL_SOURCES := $(filter-out %:Zone.Identifier,$(wildcard tpu_source_code/*.v) $(wildcard tpu_source_code/*.sv))

define VIVADO_RUN
	bash -c "source $(VIVADO_SETTINGS) && vivado $(VIVADO_OPTS) $(1)"
endef

.PHONY: mem-ip mem-bitstream clean

mem-ip: $(RTL_SOURCES) scripts/package_legacy_mem_ip.tcl
	@echo "Packaging legacy tpu_top_v6 IP..."
	@mkdir -p $(IP_REPO_DIR)
	$(call VIVADO_RUN,-source scripts/package_legacy_mem_ip.tcl -tclargs \
		-ip_name tpu_top_v6 \
		-ip_version 1.0 \
		-ip_vendor xilinx.com \
		-ip_library user \
		-part $(PART) \
		-rtl_dir tpu_source_code \
		-repo_out $(IP_REPO_DIR))

mem-bitstream: mem-ip scripts/build_legacy_mem_bitstream.tcl
	@echo "Building legacy baseline bitstream..."
	@mkdir -p $(ARTIFACTS_DIR) $(DEPLOY_DIR)
	$(call VIVADO_RUN,-source scripts/build_legacy_mem_bitstream.tcl -tclargs \
		-proj_name legacy_mem_system \
		-part $(PART) \
		-ip_repo_path $(IP_REPO_DIR) \
		-out_dir $(BUILD_DIR) \
		-bd_name design_1)
	cp -f $(ARTIFACTS_DIR)/design_1.bit $(DEPLOY_DIR)/CornellTPU.bit
	cp -f $(ARTIFACTS_DIR)/design_1.hwh $(DEPLOY_DIR)/CornellTPU.hwh
	@ls -lh $(DEPLOY_DIR)/CornellTPU.bit $(DEPLOY_DIR)/CornellTPU.hwh

clean:
	rm -rf $(BUILD_DIR) pkg_tpu_top_v6_proj .Xil vivado*.log vivado*.jou vivado*.backup.log
