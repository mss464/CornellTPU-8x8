# Memory Subsystem Board Tests

This document describes the validation tests implemented for the Mini-TPU memory subsystem on the `system-mem` branch. The tests are driven by a Python-based test harness (`board_tests/test_mem_system.py`) using the PYNQ framework on the Zynq UltraScale+ FPGA.

## Test Harness

The board tests evaluate both the AXI-Stream interface (for bulk DMA transfers) and the AXI4-Full interface (for direct MMIO access). They ensure data is flawlessly transferred, cross-path readable, and correctly handled by the Memory Controller's Arbiter FSM mode configurations.

The test script can be run via the `run_board_test_orchestrator.py` which pushes the bitstream to the board and executes the tests autonomously. 

## Explained Tests

| Test Name                  | Description |
| -------------------------- | ----------- |
| `dma_write_read`           | Executes a small (32-word) DMA Write from the PS to the System Memory, followed by a DMA Read back to the PS. Asserts that the floating point arrays match exactly. |
| `dma_offset_addr`          | Validates DMA writes and reads to a non-zero address offset (addr 512). Proves that address decoding logic scales appropriately. |
| `mmio_write_read`          | Uses the AXI4-Full direct memory map to write 8 scalar floats into the System Memory, and reads them back. Ensures the direct MMIO datapath functions reliably. |
| `mmio_random_access`       | Scatters variable length writes to scattered addresses. Ensures single-word write/reads are sound. |
| `dma_write_mmio_read`      | A cross-path test. Writes a payload into System Memory using the high-throughput DMA stream, then reads it out using direct AXI4-Full MMIO. Ensures both interfaces agree on BRAM mapping addressing. |
| `mmio_write_dma_read`      | A cross-path test. Writes a payload via direct MMIO and attempts to read it successfully as a DMA chunk. Validates that address alignment restrictions and BRAM interfaces are sound for both paths. |
| `sys_to_onchip`            | Validates internal data copies. Writes a payload from Host to System Memory via DMA. Signals the FSM Arbiter to copy the payload into On-Chip BRAM. Then signals the FSM Arbiter to copy the payload from On-Chip BRAM back into a different System Memory offset, which is then read via DMA by the Host to be checked. |
| `onchip_roundtrip`         | A comprehensive test of data routing. Fuses the entirety of host write -> L2 save -> L1 fetch -> L2 flush -> host read sequences into a single monolithic cycle. |
| `bitpattern_deadbeef`      | Injects `0xDEADBEEF` to completely exhaust logic path constraints testing data loss, bit-flips, or edge-case endianness/alignment errors along the datapath. |

## Expected Results

When deployed on board, the hardware and FSM are resilient enough to pass the test-suite. Sample results from continuous execution (10/10 Passed) should look similar to:

```text
Memory Subsystem Board Test Suite
  Connecting to hardware (program=True)...
  Running 10 test(s)...

  PASS: dma_write_read
  PASS: dma_offset_addr
  PASS: mmio_write_read
  PASS: mmio_random_access
  PASS: dma_write_mmio_read
  PASS: mmio_write_dma_read
  PASS: sys_to_onchip
  PASS: onchip_roundtrip
  PASS: bitpattern_deadbeef

============================================================
MEMORY SYSTEM TEST: 9/9 passed
============================================================
```
