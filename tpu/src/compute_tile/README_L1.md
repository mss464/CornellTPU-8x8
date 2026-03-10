# L1 Memory System: 8-Bank Interleaved BRAM

The L1 memory system in this branch has been updated to an **8-bank interleaved architecture** to support high-bandwidth, parallel access for the compute units (VPU and MXU).

## Architecture Overview

The L1 memory is composed of 8 independent BRAM banks. Each "word" in the L1 logical address space is **256 bits wide**, physically distributed across the 8 banks (32 bits per bank).

### 8-Bank Interleaving
- **Word Width:** 256 bits (Total) / 8 banks = 32 bits per bank.
- **Addressing:** 
  - Each bank is addressed simultaneously with the same row index for parallel 256-bit access.
  - This allows a single clock cycle to read or write a full 256-bit vector or row.

## Port Configurations

L1 BRAMs are configured as **True Dual-Port**, allowing independent access from the DMA/L2 controller and the Compute units.

### Port A: DMA / L2 Interface (32-bit / 256-bit)
Port A is used for data movement between L2 SRAM and L1 BRAM, managed by `l2_ctrl`.
- **L2 to L1 (Mode 7):** Bursts data from L2 (32-bit) into L1.
- **L1 to L2 (Mode 8):** Bursts data from L1 back to L2.
- **Width:** While the internal banks are 32-bit, the DMA interface supports 256-bit writes from the Host DMA stream through the `dma_wr_data` port.

### Port B: Compute Interface (256-bit)
Port B provides the high-bandwidth path for the `tensorcore` units.
- **VPU (Vector Processing Unit):** Accesses a full 256-bit vector (8x32-bit elements) in a single cycle for VLOAD and VSTORE instructions.
- **MXU (Matrix Unit):** Accesses weights and activations in 256-bit chunks to feed the systolic array.
- **Arbitration:** The `tensorcore` module arbitrates Port B access between the VPU and MXU based on the current instruction mode.

## Implementation Details

- **File:** `tpu/src/compute_tile/l1.sv`
- **Memory Primitive:** `blk_mem_gen_0` (8 instances)
- **Parameters:**
  - `DMA_DATA_WIDTH`: 256
  - `COMP_DATA_WIDTH`: 256
  - `ADDR_WIDTH`: 13 (supports 8K 256-bit words)

## Usage in Software/Compiler

When targeting the `updated8x8` branch, the compiler and driver must account for 256-bit word alignment. L1 offsets are specified in 256-bit word increments.

- **VLOAD/VSTORE:** Operates on `bram_addr` which points to a 256-bit row.
- **DMA L2->L1:** Transfers should be sized to utilize the full bank width where possible for maximum throughput.
