# Mini-TPU Verification Suite

This directory contains verification tools for the Mini-TPU project, organized by the level of the system they test.

## 1. Compute Unit Verification (`compute_tile/`)
RTL-level verification for the core TPU logic (TensorCore, MXU, VPU). Uses cocotb and Icarus Verilog.

**Run from project root:**
```bash
make -C tpu verify-compute_unit
```

## 2. System Verification (`system/`)
Hardware-in-the-loop tests intended to be executed on the physical FPGA (Ultra96-v2) to verify system integration and data paths.

### System Bus Diagnosis (`diagnose_ip.py`)
A low-level connectivity check that verifies if the ARM processor can communicate with the TPU and DMA IP blocks over the AXI bus. Use this if the hardware hangs or is unresponsive.

**Run from project root:**
```bash
make -C tpu verify-system_bus
```

### Data Integrity Test (`test_data_integrity.py`)
Verifies the integrity of the data path by writing and reading back patterns to the TPU BRAM via DMA. This ensures that the AXI-Stream interfaces and memory mapping are correct.

**Run from project root:**
```bash
make -C tpu verify-system_data
```

---

## Running Individual Tests
For board-level tests, ensure you have a valid `hw_config.json` in the `tpu/` directory or the deployment path. The tests will automatically detect the hardware configuration.
