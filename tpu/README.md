# TPU

## Reference

![Ironwood architecture](ironwood-architecture.png)

## FPGA Flow Overview

The FPGA build flow packages the portable TensorCore RTL into a Vivado IP, then
builds a board-specific block design and bitstream using board Tcl scripts.

Stages:
1. **TensorCore IP**: Package `tpu/TensorCore/*.sv` into a reusable IP.
2. **TPU IP**: Wrap TensorCore with board-specific AXI/stream interfaces.
3. **Bitstream**: Build block design + implementation → `.bit` and `.hwh`.

## Supported Targets

| Target | Status | Notes |
|--------|--------|-------|
| ultra96-v2 | ✅ Supported | Zynq UltraScale+ MPSoC flow (Vivado) |
| alveo-u280 | ⏳ Planned | Vitis/XRT flow to be added |
| alveo-v80 | ⏳ Planned | Vitis/XRT flow to be added |

## Quick Start (Ultra96-v2)

```bash
# From repo root
make -C tpu tensorcore-ip
make -C tpu bitstream TARGET=ultra96-v2
```

## Manual Vivado Usage (Ultra96-v2)

```bash
# Package TPU IP
vivado -mode batch -source tpu/ultra96-v2/package_tpu_ip.tcl -tclargs \
    -ip_name cornell_tpu \
    -part xczu3eg-sbva484-1-i \
    -rtl_dir tpu/TensorCore \
    -rtl_dir tpu/ultra96-v2/rtl \
    -repo_out tpu/ultra96-v2/ip_repo

# Build block design + bitstream
vivado -mode batch -source tpu/ultra96-v2/build_bd_bitstream.tcl -tclargs \
    -proj_name tpu_system \
    -part xczu3eg-sbva484-1-i \
    -ip_repo_path tpu/ultra96-v2/ip_repo \
    -out_dir tpu/ultra96-v2/output
```

## Build Outputs (Ultra96-v2)

After a successful build, artifacts are in `tpu/ultra96-v2/output/artifacts/`:

| File | Description |
|------|-------------|
| `minitpu.bit` | FPGA bitstream (~5.5 MB) |
| `minitpu.hwh` | Hardware handoff for PYNQ (~343 KB) |
| `utilization_report.txt` | Resource usage summary |
| `timing_summary.txt` | Timing analysis |
| `power_report.txt` | Power estimates |

**Typical utilization (xczu3eg):**
- LUTs: ~24%
- Registers: ~8%
- DSPs: 34 (for FP32 multiply)
- Clock: 50 MHz (WNS ~3ns positive slack)

## Validation

Run FPGA tests after building:

```bash
make -C tests board-test \
    BIT=tpu/ultra96-v2/output/artifacts/minitpu.bit \
    HWH=tpu/ultra96-v2/output/artifacts/minitpu.hwh \
    PROGRAM=tests/fpga/test_comprehensive.py
```

## Documentation

Detailed documentation for the system architecture and memory design can be found in the `docs/` directory:

- [System Architecture](docs/system_architecture.md): Overview of the interconnect and tile-based design.
- [Memory Design](docs/memory_design.md): Deep dive into the memory hierarchy, AXI interfaces, and DMA flow.
- [Test Explanation](docs/test_explanation.md): Details of the board-level verification suite.

## Notes

- Source Vivado settings before building:
  `source /opt/xilinx/Vitis/2023.2/settings64.sh`
- Board-specific files live under `tpu/<target>/`.
- IP instance name in block design is `tpu_0` (used by `pynq_host.py` driver).
