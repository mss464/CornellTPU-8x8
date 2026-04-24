# Memory Subsystem Board Tests

This document describes the validation tests implemented for the Mini-TPU memory subsystem. The tests are driven by a Python-based test harness (`board_tests/test_mem_system.py`) using the PYNQ framework on the Zynq UltraScale+ FPGA.

## Test Harness

The board tests evaluate the AXI-Stream interface (for bulk DMA transfers) and internal memory movement between LPDDR4 and On-chip BRAM. They ensure data is flawlessly transferred and correctly handled by the Memory Controller's Arbiter FSM mode configurations.

Due to the ARMv8 architecture of the Zynq UltraScale+, the driver uses **cacheable memory** for CMA buffers to prevent `SIGBUS` errors during vectorized operations. Hardware-level synchronization ensures that AXI transactions are fully committed before the host is notified.

## Explained Tests

| Test Name                  | Description |
| -------------------------- | ----------- |
| `dma_write_read`           | Executes a small (32-word) DMA Write from the PS to the System Memory (DDR), followed by a DMA Read back to the PS. Asserts that the floating point arrays match exactly. |
| `dma_large_transfer`       | Validates bulk transfer capability with 1024 words (4KB). Tests the stability of the AXI-Stream to AXI-Master conversion logic. |
| `dma_offset_addr`          | Validates DMA writes and reads to a non-zero address offset (addr 512). Proves that address decoding logic scales appropriately. |
| `sys_to_onchip`            | Validates internal data copies. Writes a payload from Host to System Memory (DDR) via DMA. Signals the FSM Arbiter to copy the payload into On-Chip BRAM. Then signals a copy back to a different DDR offset, which is then verified. |
| `onchip_roundtrip`         | A comprehensive test of data routing. Fuses the entirety of host write -> DDR save -> L1 BRAM fetch -> DDR flush -> host read sequences into a single monolithic cycle. |
| `bitpattern_deadbeef`      | Injects `0xDEADBEEF` to check for bit-flips or edge-case endianness/alignment errors along the 256-bit datapath. |

## Troubleshooting & Requirements

### 1. Register Units
The `length` register (0x18) in hardware expects the number of **256-bit beats** (32-byte chunks), not the byte count. The driver handles this translation automatically.

### 2. Cache Coherency
If using the `MemDriver` manually, ensure that:
- `allocate(..., cacheable=True)` is used.
- `sync_to_device()` is called before starting a DMA Write (Mode 1).
- `invalidate()` is called after a DMA Read (Mode 2) completes to clear the CPU cache.

### 3. AXI4-Full MMIO
The current system architecture prioritize high-bandwidth DMA via the HP0 port. AXI4-Full MMIO access to DDR is currently bypassed in the driver initialization if the corresponding slave segment is not mapped in the PYNQ overlay.

## Expected Results

Sample results from a successful execution:

```text
Memory Subsystem Board Test Suite
Connecting to hardware (program=False)...
Memory subsystem ready (ctrl=<pynq.overlay.DefaultIP object at 0x7fb2b01320>, dma=<pynq.lib.dma.DMA object at 0x7fb2b06630>)
Allocated Device Memory backend at phys: 0x78900000
Running 9 test(s)...

  PASS: dma_write_read
  PASS: dma_large_transfer
  PASS: dma_offset_addr
SKIP: mmio_write_read  — AXI4-Full MMIO not available
SKIP: mmio_random_access  — AXI4-Full MMIO not available
SKIP: dma_write_mmio_read  — AXI4-Full MMIO not available
SKIP: mmio_write_dma_read  — AXI4-Full MMIO not available
  PASS: sys_to_onchip
  PASS: onchip_roundtrip
  PASS: bitpattern_deadbeef

Test Results:
  Passed:  6
  Failed:  0
  Skipped: 3
```
