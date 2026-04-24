# Mini-TPU System Memory Design

This document details the architecture and connectivity of the memory subsystem on the `system-mem` branch, integrated into the Mini-TPU design.

## Architecture & Hierarchy

The memory subsystem bridges the host Processing System (PS) and the internal compute resources (like the Tensor Core) on the Programmable Logic (PL). It consists of two main memory levels:

1.  **System Memory (External DDR4/LPDDR4):**
    -   Acts as the primary bulk storage for data coming from the host and results waiting to be retrieved.
    -   Implemented using physical **LPDDR4 memory** on the Ultra96 board (accessed via the Zynq HP0 port).
    -   Accessed via Direct Memory Access (DMA) for fast bulk transfers or directly mapped via AXI4-Full MMIO (optional).
    -   The hardware manages the physical address translation relative to a `ddr_phys_base` register provided by the driver.

2.  **On-Chip Memory (L1/Scratchpad BRAM):**
    -   The fast, internal scratchpad memory directly interfacing with the processing units.
    -   Data is loaded into the On-Chip Memory from the System Memory (DDR) before computation, and results are written back to System Memory afterwards.
    -   Width: 256-bit to match TensorCore requirements.

## Interfaces & Connectivity

The Subsystem leverages the AXI standard for communication between the PS Host and the TPU PL.

-   **AXI-Lite Slave (Control):** Used for configuration and status.
    -   **Decoupled Handshake:** The FSM is fully AXI-compliant, handling decoupled Address (`AWVALID`) and Data (`WVALID`) phases.
    -   Exposes control registers (Mode, Source/Destination Address, Transfer Length, and a Doorbell register).
-   **AXI-Stream Slave (DMA Write):** Provides a high-throughput, unidirectional channel (DMA Write) from the PS to the System Memory (DDR). Transfers use 256-bit wide data beats.
-   **AXI-Stream Master (DMA Read):** Provides a high-throughput, unidirectional channel (DMA Read) from the System Memory (DDR) back to the PS.
-   **AXI4 Master (DDR Port):** A high-performance 128-bit/256-bit master interface connected to the Zynq PS HP0 port to access physical DDR memory.

## Register Map (AXI-Lite)

| Register | Offset | Description |
|----------|--------|-------------|
| `mode` | 0x00 | [3:0]=Mode, [4]=Doorbell (Self-clearing) |
| `status` | 0x04 | Bit 0 = Idle (1 = System is ready for next command) |
| `stream_ready` | 0x08 | Bit 0 = AXI-Stream interface ready for DMA |
| `addr_sys` | 0x0C | Word offset in System Memory (relative to base) |
| `addr_onchip` | 0x10 | Word offset in On-Chip Memory |
| `length` | 0x18 | **Transfer length in 256-bit (32-byte) beats** |
| `ddr_phys_base` | 0x1C | Base physical address of CMA buffer in PSDDR |

## Operations and Data Flow (Modes)

The TPU memory controller (`device_mem.sv`) implements an Arbiter FSM that responds to the AXI-Lite Doorbell register to orchestrate different transfer modes:
-   **Mode 1 (DMA Write):** PS Host streams data from its memory into System Memory (DDR).
-   **Mode 2 (DMA Read):** System Memory (DDR) data is streamed back to the PS Host.
-   **Mode 5 (SYS_TO_OC):** System Memory internally copies a block of data from DDR to On-Chip Memory BRAM.
-   **Mode 6 (OC_TO_SYS):** On-Chip Memory BRAM internally copies a block of data back to System Memory (DDR).

### Synchronization & Coherency
-   **Driver-Level:** The PYNQ driver must use `cacheable=True` memory with explicit `sync_from_device()` / `sync_to_device()` calls to ensure ARMv8 CPU cache coherency.
-   **Hardware-Level:** The `done` status is gated by the LPDDR4 controller's idle state to ensure the host doesn't read data before the final burst is written to DDR.

## Subsystem Diagram

```mermaid
graph TD
    %% Host and AXI Interconnect Layer
    Host[PS Host (PYNQ / ARM Core)]
    DDR[Physical LPDDR4 Memory]
    
    %% Connections from Host
    Host -- AXI-Lite --> CtrlReg[Control Registers & Doorbell]
    Host -- AXI-Stream --> DMA_in[AXI-Stream Slave]
    DMA_out[AXI-Stream Master] -- AXI-Stream --> Host

    subgraph TPU Memory Subsystem `tpu.sv`
        CtrlReg -. Controls .-> mem_ctrl[Memory Controller FSM]
        
        %% Streams to sys_mem
        DMA_in -- 256-bit beat --> mem_ctrl
        mem_ctrl -- 256-bit beat --> DMA_out

        %% AXI Master to DDR
        mem_ctrl -- AXI4 Master Burst --> DDR
        
        %% Internal Copy
        mem_ctrl <== 256-bit Internal Link ==> onchip_mem[On-Chip Memory BRAM]
    end
    
    style Host fill:#f9f,stroke:#333,stroke-width:2px
    style DDR fill:#ff9,stroke:#333,stroke-width:2px
    style onchip_mem fill:#cfc,stroke:#333,stroke-width:2px
```
