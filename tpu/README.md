# Optimized Mini-TPU Memory Subsystem

This directory contains the Ultra96-v2 optimized memory subsystem, the compute
RTL it integrates, the PYNQ runtime, board tests, benchmarks, and design docs.

## Architecture

The design has three hardware-facing memory levels:

| Level | Module | Role |
| ----- | ------ | ---- |
| Host DMA buffers | PYNQ / AXI DMA | Source and sink for board payloads. |
| System memory | `src/system/device_mem.sv` | 8-bank BRAM staging area with wide DMA and scalar MMIO/copy ports. |
| L1 scratchpad | `tensorcore/scratchpad.sv` | 8-bank compute scratchpad used by MXU, VADD, and VPU programs. |

`src/system/mem_top.sv` ties the design together with:

- AXI-Lite control/status registers.
- AXI-Stream DMA write and read paths.
- AXI4-Full direct MMIO into system memory.
- Independent memory-copy and compute controllers.
- Instruction RAM loading through DMA mode 4.

## Build

```bash
cd tpu
source /opt/xilinx/Vitis/2023.2/settings64.sh
make mem-bitstream
```

Build artifacts are written to:

```text
ultra96-v2/output/artifacts/mem_bd.bit
ultra96-v2/output/artifacts/mem_bd.hwh
```

## Board Tests

```bash
make mem-board-tests BOARD_IP=132.236.59.72
make concurrency-test BOARD_IP=132.236.59.72
```

Pass focused test options with `BOARD_TEST_ARGS`:

```bash
make mem-board-tests BOARD_IP=132.236.59.72 BOARD_TEST_ARGS="--test dma_write_read --verbose"
```

## Benchmarks

Run the benchmark against the current checkout:

```bash
make mem-benchmark BOARD_IP=132.236.59.72 BENCH_ARGS="--repeats 5 --warmups 1"
```

For A/B comparisons against another checkout, use:

```bash
bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu/tpu \
  --variant opt-mem-strength \
  --board-ip 132.236.59.72 \
  --out results/opt-mem-strength.json \
  --bench-args "--repeats 5 --warmups 1 --sizes 1024,4096,8192 --copy-sizes 1024,2048,4096 --vadd-len 2048 --vadd-repeats 128 --mxu-repeats 128 --vpu-elems 248 --dma-words 8192"
```

See `benchmarks/README.md` for the full baseline/candidate comparison flow.

## Directory Map

```text
tpu/
  Makefile
  src/
    system/               AXI, DMA, MMIO, memory, copy, and compute-control RTL
    compute_tile/         Compute tile integration wrapper
  tensorcore/             MXU, VPU, VADD, scratchpad, decoder, and PC RTL
  runtime/                PYNQ host runtime
  board_tests/            Hardware tests
  benchmarks/             Benchmark and comparison scripts
  scripts/                Vivado packaging and bitstream TCL
  docs/                   Design notes and diagrams
```

## Documentation

- `docs/system_architecture.md`: high-level block diagram.
- `docs/memory_design.md`: memory hierarchy and doorbell modes.
- `docs/MEMORY_SYSTEM.md`: register/data-path contract.
- `docs/test_explanation.md`: board test notes.
- `docs/interactive_memory_flow.html`: interactive data-flow visualization.
