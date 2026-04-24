# Mini-TPU System Memory Design

This document details the architecture and connectivity of the memory subsystem on the `system-mem` branch, integrated into the Mini-TPU design.

## Architecture & Hierarchy

The memory subsystem bridges the host Processing System (PS) and the internal compute resources (like the upcoming Tensor Core) on the Programmable Logic (PL). It consists of two main memory levels implemented in block RAM (BRAM):

1.  **System Memory (L2/Main BRAM):**
    -   Acts as the primary bulk storage for data coming from the host and results waiting to be retrieved.
    -   Address space is exposed via the AXI interconnect.
    -   Accessed via Direct Memory Access (DMA) for fast bulk transfers or directly mapped via AXI4-Full MMIO for single word access.

2.  **On-Chip Memory (L1/Scratchpad BRAM):**
    -   The fast, internal scratchpad memory directly interfacing with the processing units.
    -   Data is loaded into the On-Chip Memory from the System Memory before computation, and results are written back to the System Memory afterwards.

## Interfaces & Connectivity

The Subsystem leverages the AXI standard for communication between the PS Host and the TPU PL.

-   **AXI-Lite Slave (Control):** Used for configuration. Exposes memory-mapped control registers (Mode, Source/Destination Address, Transfer Length, and a Doorbell register to initiate operations).
-   **AXI-Stream Slave (DMA Write):** Provides a high-throughput, unidirectional channel (DMA Write) from the PS to the System Memory. Transfers use 256-bit wide data beats.
-   **AXI-Stream Master (DMA Read):** Provides a high-throughput, unidirectional channel (DMA Read) from the System Memory back to the PS.
-   **AXI4-Full Slave (MMIO):** Allows direct read/write MMIO access to the System Memory array by the PS, completely bypassing the DMA engines. This is ideal for fine-grained scalar variable access.

## Operations and Data Flow (Modes)

The TPU memory controller (`mem_ctrl.sv`) implements an Arbiter FSM that responds to the AXI-Lite Doorbell register to orchestrate different transfer modes:
-   **Mode 1 (DMA Write):** PS Host streams data into System Memory.
-   **Mode 2 (DMA Read):** System Memory data is streamed back to the PS Host.
-   **Mode 5 (SYS_TO_OC):** System Memory internally copies a block of data to On-Chip Memory.
-   **Mode 6 (OC_TO_SYS):** On-Chip Memory internally copies a block of data back to System Memory.

## Subsystem Diagram

```mermaid
graph TD
    %% Host and AXI Interconnect Layer
    Host[PS Host (PYNQ / Zynq)]
    
    %% Connections from Host
    Host -- AXI-Lite --> CtrlReg[Control Registers & Doorbell]
    Host -- AXI-Stream (DMA Write) --> DMA_in[AXI-Stream Slave]
    Host -- AXI4-Full (MMIO) --> sys_mem
    DMA_out[AXI-Stream Master] -- AXI-Stream (DMA Read) --> Host

    subgraph Memory Subsystem Top `mem_top.sv`
        CtrlReg -. Controls .-> mem_ctrl[Memory Controller FSM Arbiter]
        
        %% Streams to sys_mem
        DMA_in -- 256-bit data beat --> sys_mem[System Memory BRAM 16-bit Addr]
        sys_mem -- 256-bit data beat --> DMA_out

        %% mem_ctrl orchestrates internal moves
        mem_ctrl -- Mode 5 / Mode 6 control --> sys_mem
        mem_ctrl -- Mode 5 / Mode 6 control --> onchip_mem[On-Chip Memory BRAM 15-bit Addr]
        
        sys_mem <== Internal Data Copy ==> onchip_mem
    end
    
    style Host fill:#f9f,stroke:#333,stroke-width:2px
    style sys_mem fill:#bbf,stroke:#333,stroke-width:2px
    style onchip_mem fill:#cfc,stroke:#333,stroke-width:2px
```
