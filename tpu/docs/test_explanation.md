# Board Test Notes

The board tests validate the optimized memory subsystem on the Ultra96-v2 PYNQ
board. They use `runtime/pynq_host.py` and the generated `mem_bd.bit` /
`mem_bd.hwh` artifacts.

## Test Programs

| File | Purpose |
| ---- | ------- |
| `board_tests/test_mem_system.py` | DMA, MMIO, system-memory/L1 copy, and bit-pattern tests. |
| `board_tests/test_concurrency.py` | Overlapped compute and DMA behavior. |

## Useful Commands

```bash
cd tpu
make mem-bitstream
make mem-board-tests BOARD_IP=<board-ip>
make concurrency-test BOARD_IP=<board-ip>
```

Extra test arguments can be passed through `BOARD_TEST_ARGS`:

```bash
make mem-board-tests BOARD_IP=<board-ip> BOARD_TEST_ARGS="--test dma_write_read --verbose"
```

## Coverage

The tests exercise:

- AXI DMA writes and reads through the stream adapters.
- AXI4-Full MMIO writes and reads when the Vivado address map exposes the
  `s01_axi` segment.
- Internal system-memory to L1 and L1 to system-memory copies.
- Endianness and alignment-sensitive bit patterns.
- Compute/DMA overlap used by the benchmark double-buffering row.
