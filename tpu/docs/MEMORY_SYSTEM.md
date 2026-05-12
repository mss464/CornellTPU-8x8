# Memory System Notes

This document summarizes the hardware contract used by the runtime, board
tests, and benchmark suite.

## Control Registers

| Offset | Register | Description |
| ------ | -------- | ----------- |
| `0x00` | mode/doorbell | Mode in bits `[3:0]`; doorbell trigger in bit `[4]`; latency selection in bit `[7]`. |
| `0x04` | status | `compute_idle`, `dma_idle`, and stream status bits. |
| `0x0C` | addr_sys | 32-bit word address in system memory. |
| `0x10` | addr_onchip | 32-bit word address in L1 scratchpad. |
| `0x18` | length | Transfer length in bytes. |

## Data Paths

- Host DMA write: PYNQ buffer -> AXI DMA MM2S -> `tpu_slave_axi_stream.v` ->
  `device_mem.sv`.
- Host DMA read: `device_mem.sv` -> `tpu_master_axi_stream.v` -> AXI DMA S2MM
  -> PYNQ buffer.
- MMIO: host AXI4-Full reads/writes go through `axi_full_slave.sv` into the
  scalar port of `device_mem.sv`.
- Internal copy: `mem_ctrl.sv` moves 32-bit words between system memory and the
  L1 scratchpad.
- Compute: `compute_ctrl.sv` launches `compute_tile.sv`, which fetches
  instructions and drives the TensorCore modules.

## Benchmark-Relevant Behavior

- DMA uses 256-bit internal rows, exposed through a 128-bit AXI DMA boundary in
  the Vivado block design.
- System memory and L1 both expose banked rows, enabling the SIMD VPU benchmark
  to exercise the 8-lane path.
- Compute and DMA have separate idle signals. The benchmark uses those signals
  to measure overlapped compute plus next-tile DMA when supported.
- Program state is reset/fetched before benchmark launches so repeated runs can
  report stable median timing.
