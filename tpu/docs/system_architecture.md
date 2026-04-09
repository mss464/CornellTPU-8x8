# Mini-TPU System Architecture

This document provides a high-level overview of the Mini-TPU system architecture, including the interconnect, compute tiles, and memory hierarchy.

## Block Diagram

Below is the high-level representation of the system components and their connectivity:

```text
              ┌─────────────── AXI NoC (3×2 mesh) ─────────┐
              │                                            │
         ┌────┴─────┐                                ┌─────┴────┐
         │ Compute  │◄──────────────────────────────►│ Compute  │
         │ Tile 0   │                                │ Tile 1   │
         │(MXU+VPU  │                                │(MXU+VPU  │
         │ +L1)     │                                │ +L1)     │
         └────┬─────┘                                └─────┬────┘
              │                                            │
              ▼                                            ▼
         ┌──────────┐                                ┌──────────┐
         │ Compute  │◄──────────────────────────────►│ Compute  │
         │ Tile 2   │                                │ Tile 3   │
         │(MXU+VPU  │                                │(MXU+VPU  │
         │ +L1)     │                                │ +L1)     │
         └────┬─────┘                                └─────┬────┘
              │                                            │
              ▼                                            ▼
         ┌──────────────────────────────────────────────────────┐
         │ 			L2 Tile	        		│
         │ 			(shared           		│
         │  			  SRAM)            		│
         └────┬─────────────────────────────────────────────────┘
              │				     	     ┌──────────┐
              │ 				     │ Control  │
              │				     	     │  Tile    │
              │				             │(host ctl)│
              │				     	     └──┬───┬───┘
              │                                    DMA  │   │
              │◄───────────────────────────────────────►│   │
              │                                   AXI-S │   │
              │ AXI-MM (HBM)                            │   │ AXI-Lite over PCIe
              │ AXI-S (DDR prototype)                   │   │
              │                                         │   │
         ┌────┴─────┐                                ┌──┴───┴───┐
         │  Device  │                                │ Host(PS) │
         │  Memory  │                                │          │
         │(DDR/HBM) │                                │          │
         └──────────┘                                └──────────┘
```

## Key Components

- **Compute Tiles (0-3):** Each tile contains a Matrix Unit (MXU), Vector Processing Unit (VPU), and L1 Scratchpad memory. They are connected via a 2D mesh AXI NoC.
- **L2 Tile:** A shared SRAM providing intermediate storage for all compute tiles.
- **Control Tile:** Manages the orchestration of computations and DMA transfers between host and device memory.
- **AXI NoC (3x2 mesh):** Provides high-bandwidth interconnect between compute tiles and the L2 tile.
- **Device Memory:** External DDR or HBM storage for large datasets.
- **Host (PS):** The host processor (e.g., Zynq PS) that controls the TPU via AXI-Lite and AXI-Stream.

## Connectivity

- **AXI-Lite over PCIe:** Command and control interface from host to control tile.
- **AXI-Stream (DMA):** Fast data transfer path between host and L2 tile.
- **AXI-MM (HBM):** Memory-mapped interface to external high-bandwidth memory.
- **AXI-S (DDR prototype):** Stream interface for DDR prototyping.
