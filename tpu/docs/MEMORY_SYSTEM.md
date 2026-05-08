# Mini-TPU Memory Subsystem Performance & Architecture

This document describes the performance specifications and data flow of the current Mini-TPU memory subsystem on the Ultra96-v2 board.

## Performance Specifications

| Component | Bit Width | Clock Speed | Max Throughput |
| :--- | :--- | :--- | :--- |
| **AXI-DMA** | 128-bit | 100 MHz | 1.6 GB/s |
| **Stream Interconnect** | 128-bit | 100 MHz | 1.6 GB/s |
| **Internal Data Path** | 256-bit | 100 MHz | 3.2 GB/s |
| **LPDDR4 Memory** | 64-bit (32-bit x 2) | 533 MHz | ~4.2 GB/s |

## Data Flow & Path

### 1. Host-to-TPU (DMA Write)
1.  **Host CPU**: Writes data to a contiguous `pynq.allocate` buffer in System RAM.
2.  **AXI-DMA (MM2S)**: Reads the buffer from System RAM and streams it to the FPGA at **128 bits per clock**.
3.  **TPU Slave Stream**:
    - Receives two 128-bit beats from the AXI-DMA.
    - Concatenates them into a single **256-bit word**.
    - Passes the 256-bit word to the memory controller.
4.  **Device Mem (AXI Master)**:
    - Receives the 256-bit word.
    - Issues an AXI4-Full write burst of length 2 (each beat is 128 bits) to the **PS LPDDR4** controller via the HP0 port.

### 2. TPU-to-Host (DMA Read)
1.  **Device Mem (AXI Master)**:
    - Issues an AXI4-Full read burst of length 2 from LPDDR4.
    - Concatenates the two 128-bit beats into a single **256-bit word**.
2.  **TPU Master Stream**:
    - Receives the 256-bit word.
    - Splits it into two **128-bit beats**.
    - Sends the beats to the AXI-DMA (S2MM) port.
3.  **AXI-DMA (S2MM)**: Receives the 128-bit stream and writes it back to the Host CPU's buffer in System RAM.

## Critical Handshaking & Synchronization

-   **Doorbell Mechanism**: The host triggers an operation by writing to `slv_reg0`. The hardware clears the doorbell bit immediately after latching the command to signal it has started.
-   **One-Shot Streams**: Both stream modules implement a `running` flag that ensures they only execute once per doorbell trigger. This prevents race conditions where a stream might re-trigger if the doorbell hasn't been cleared fast enough.
-   **Word Alignment**: The hardware expects transfer lengths to be multiples of 32 bytes (one 256-bit word).

## Memory Map

| Register | Address | Description |
| :--- | :--- | :--- |
| `slv_reg0` | `0x00` | Doorbell [31] + Mode [3:0] |
| `slv_reg1` | `0x04` | Debug Status (FSM States, Pointers, IRDY) |
| `slv_reg4` | `0x10` | Base System Address (offset in DDR) |
| `slv_reg6` | `0x18` | Transfer Length (bytes) |
| `slv_reg10` | `0x28` | DDR Physical Base Address |
