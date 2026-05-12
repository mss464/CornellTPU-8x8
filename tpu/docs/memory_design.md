# Optimized Memory Design

The optimized memory design connects the Ultra96-v2 host, DMA engine, on-chip
system memory, L1 scratchpad, and compute tile through a small set of explicit
hardware modes.

## Memory Hierarchy

| Level | Implementation | Width | Purpose |
| ----- | -------------- | ----- | ------- |
| Host memory | PYNQ DMA buffers in PS memory | 128-bit DMA stream | Source and sink for board tests and benchmarks. |
| System memory | 8-bank PL BRAM in `device_mem.sv` | 256-bit DMA port, 32-bit scalar port | Bulk staging memory for DMA, MMIO, and copies. |
| L1 scratchpad | 8-bank PL BRAM in `scratchpad.sv` | 256-bit compute port, 32-bit copy port | Compute working set for MXU, VADD, and VPU programs. |
| Instruction RAM | BRAM inside `compute_tile.sv` | 64-bit instruction words | Program storage loaded through DMA mode 4. |

## Interfaces

- AXI-Lite `s00_axi`: control/status registers and doorbell.
- AXI-Stream `s00_axis`: DMA write path from host to system memory or IRAM.
- AXI-Stream `m00_axis`: DMA read path from system memory to host.
- AXI4-Full `s01_axi`: direct host MMIO into system memory for small random
  transfers.

## Doorbell Modes

| Mode | Operation |
| ---- | --------- |
| 1 | DMA write from host into system memory. |
| 2 | DMA read from system memory back to host. |
| 3 | Compute launch from instruction RAM. |
| 4 | DMA write into instruction RAM. |
| 5 | Copy system memory to L1 scratchpad. |
| 6 | Copy L1 scratchpad to system memory. |

The host writes the mode and doorbell bit through AXI-Lite. Hardware latches the
command, clears the doorbell, runs the selected FSM, and exposes idle status so
the runtime can wait for completion.

## Optimized Compute Path

The candidate design keeps DMA and compute independently observable so the
runtime can overlap the next DMA transfer with compute. The compute controller
also supports repeated benchmark launches by resetting/fetching program state
cleanly, which makes median timing runs meaningful.

The banked VPU path uses 8-lane loads/stores through the scratchpad rows. In the
248-element benchmark, this cuts the analytical transaction count from 744
scalar transactions to 93 banked transactions.
