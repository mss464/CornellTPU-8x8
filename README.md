# CornellTPU Optimized Memory Design

This branch is a cleaned hardware-focused snapshot of the optimized Mini-TPU
memory subsystem. It keeps the files needed to build the Ultra96-v2 bitstream,
run the board tests, run the evaluation benchmarks, and document the design.

Large generated Vivado outputs, old compiler/runtime experiments, unrelated
simulation harnesses, ASIC collateral, and stale frontend code were removed so
the branch is easier to review.

## What Is Included

```text
tpu/
  Makefile                         Build, deploy, board-test, and benchmark targets
  src/system/                      Memory subsystem RTL and AXI interfaces
  src/compute_tile/                Compute tile wrapper used by the memory design
  tensorcore/                      MXU, VPU, scratchpad, decoder, and PC RTL
  runtime/pynq_host.py             PYNQ runtime used on the Ultra96-v2 board
  board_tests/                     Hardware smoke and memory/concurrency tests
  benchmarks/                      Benchmark runner and comparison scripts
  scripts/                         Vivado IP packaging and bitstream build scripts
  docs/                            Architecture, test, and benchmark documentation
```

## Quick Start

From the `tpu/` directory:

```bash
source /opt/xilinx/Vitis/2023.2/settings64.sh
make mem-bitstream

make mem-board-tests BOARD_IP=132.236.59.72
make concurrency-test BOARD_IP=132.236.59.72
make mem-benchmark BOARD_IP=132.236.59.72 BENCH_ARGS="--repeats 5 --warmups 1"
```

The bitstream artifacts are generated under:

```text
tpu/ultra96-v2/output/artifacts/mem_bd.bit
tpu/ultra96-v2/output/artifacts/mem_bd.hwh
```

## Benchmark Flow

The benchmark runner can compare this optimized design against a separate
baseline checkout:

```bash
cd tpu

bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu-mem-base-pc-reset \
  --variant mem-base-pc-reset-strength \
  --board-ip 132.236.59.72 \
  --out results/mem-base-pc-reset-strength.json \
  --bench-args "--repeats 5 --warmups 1 --sizes 1024,4096,8192 --copy-sizes 1024,2048,4096 --vadd-len 2048 --vadd-repeats 128 --mxu-repeats 128 --vpu-elems 248 --dma-words 8192"

bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu/tpu \
  --variant opt-mem-strength \
  --board-ip 132.236.59.72 \
  --out results/opt-mem-strength.json \
  --bench-args "--repeats 5 --warmups 1 --sizes 1024,4096,8192 --copy-sizes 1024,2048,4096 --vadd-len 2048 --vadd-repeats 128 --mxu-repeats 128 --vpu-elems 248 --dma-words 8192"

python3 benchmarks/compare_mem_benchmarks.py \
  results/mem-base-pc-reset-strength.json \
  results/opt-mem-strength.json
```

## Validated Results

The latest board comparison against the PC-reset baseline showed:

- 4.18x faster MXU 4x4 matmul benchmark.
- 7.06x faster 2048-word VADD benchmark with 128 repeats.
- 4.18x faster measured 248-element banked VPU vector add.
- 1.14x to 1.15x faster 8192-word host write DMA.
- 1.07x faster 8192-word host read DMA.
- 1.54x candidate double-buffer speedup over its serial estimate.

See `tpu/benchmarks/README.md` for the detailed benchmark recipes and
`tpu/docs/` for the memory architecture notes.
