# TensorCore RTL

This directory contains the compute-side SystemVerilog used by the optimized
memory subsystem.

## Key Modules

| File | Module | Purpose |
| ---- | ------ | ------- |
| `compute_core.sv` | `compute_core` | Dispatches decoded instructions to MXU, VPU, and VADD units. |
| `decoder.sv` | `decoder` | Decodes 64-bit instructions. |
| `pc.sv` | `pc` | Program counter with explicit load/reset support for repeated launches. |
| `scratchpad.sv` | `scratchpad` | 8-bank L1 scratchpad used by compute. |
| `mxu.sv` | `mxu` | Matrix unit wrapper around the systolic array. |
| `systolic.sv` | `systolic` | 4x4 systolic array. |
| `vpu_simd.sv` | `vpu_simd` | Bank-parallel SIMD VPU path. |
| `vpu.sv` / `vpu_op.sv` | `vpu`, `vpu_op` | Scalar/vector ALU support. |
| `vadd.sv` / `dummy_unit.sv` | `vadd`, `dummy_unit` | Simple vector-add datapath. |

## Integration

The memory subsystem packages these modules together with:

- `src/compute_tile/compute_tile.sv`
- `src/system/mem_top.sv`
- the AXI-Lite, AXI-Stream, and AXI4-Full system interfaces in `src/system/`

Build the integrated Ultra96-v2 design from `tpu/`:

```bash
make mem-bitstream
```

Run the board-level memory tests:

```bash
make mem-board-tests BOARD_IP=<board-ip>
```
