# Memory Benchmark Comparison

This directory contains the board benchmark flow used to compare the optimized
memory design against a separate baseline checkout.

The current A/B setup is:

- baseline: a checkout of Sunwoo's memory-system design with the legacy compute
  PC reset fix, usually `~/minitpu-mem-base-pc-reset`
- candidate: this cleaned optimized-memory branch, `opt-mem`

The scripts measure:

- host-to-system-memory DMA write latency and bandwidth
- system-memory-to-host DMA read latency and bandwidth
- host write/read round-trip latency
- system-memory to L1 copy latency
- L1 to system-memory copy latency
- VADD compute time
- MXU 4x4 matrix-multiply compute time
- measured banked 8-lane VPU vector add versus the legacy scalar VPU path
- overlapped compute plus DMA time when the runtime exposes independent waits
- an analytical 1-bank versus 8-bank L1 transaction model

## Build The Candidate

```bash
cd ~/minitpu/tpu
git checkout opt-mem
git pull --ff-only
source /opt/xilinx/Vitis/2023.2/settings64.sh
make mem-bitstream
```

The optimized checkout stores its artifacts under:

```text
ultra96-v2/output/artifacts/mem_bd.bit
ultra96-v2/output/artifacts/mem_bd.hwh
```

The legacy baseline runner also supports checkouts that store artifacts under:

```text
compiler/tpu_deploy/CornellTPU.bit
compiler/tpu_deploy/CornellTPU.hwh
```

## Strength Run

```bash
cd ~/minitpu/tpu

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

## Focused Runs

MXU only:

```bash
bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu-mem-base-pc-reset \
  --variant mem-base-pc-reset-mxu \
  --board-ip 132.236.59.72 \
  --out results/mem-base-pc-reset-mxu.json \
  --bench-args "--mxu-only --repeats 5 --warmups 1 --mxu-repeats 128"

bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu/tpu \
  --variant opt-mem-mxu \
  --board-ip 132.236.59.72 \
  --out results/opt-mem-mxu.json \
  --bench-args "--mxu-only --repeats 5 --warmups 1 --mxu-repeats 128"
```

Banked VPU only:

```bash
bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu-mem-base-pc-reset \
  --variant mem-base-pc-reset-banked-vpu \
  --board-ip 132.236.59.72 \
  --out results/mem-base-pc-reset-banked-vpu.json \
  --bench-args "--banked-vpu-only --repeats 5 --warmups 1 --vpu-elems 248"

bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu/tpu \
  --variant opt-mem-banked-vpu \
  --board-ip 132.236.59.72 \
  --out results/opt-mem-banked-vpu.json \
  --bench-args "--banked-vpu-only --repeats 5 --warmups 1 --vpu-elems 248"
```

## Current Result Summary

The latest full comparison against `mem-base-pc-reset-strength` reported:

- VADD compute: 17.470 ms baseline, 2.473 ms candidate, 7.06x faster.
- MXU 4x4 matmul: 1.315 ms baseline, 0.315 ms candidate, 4.18x faster.
- Banked VPU vector add: 1.315 ms baseline, 0.314 ms candidate, 4.18x faster.
- 8192-word host write: 1.147 ms baseline, 1.000 ms candidate, 1.15x faster.
- 8192-word host read: 1.309 ms baseline, 1.228 ms candidate, 1.07x faster.
- Candidate double buffering: 3.474 ms serial estimate, 2.253 ms overlapped,
  1.54x faster.

The comparison script prints a `Strength Scorecard` above the detailed table.
That section is the easiest output to paste into a report.
