# Memory Benchmark Comparison

This directory contains a board benchmark flow for comparing memory-system
designs across separate MiniTPU branches or checkouts.

The intended A/B setup is:

- baseline: Sunwoo's MiniTPU `memory-system` branch copied into `mem-base`
- candidate: this repository on `codex/fix-system-mem-dma-read`

The benchmark measures:

- host to system-memory DMA write bandwidth
- system-memory to host DMA read bandwidth
- system-memory to L1 copy time
- L1 to system-memory copy time
- VADD compute time
- banked 8-lane VPU vector-add time versus the legacy scalar VPU path
- overlapped compute plus DMA time, when the runtime exposes independent DMA and compute waits
- an analytical 1-bank vs 8-bank L1 model for wide vector-access speedup

## Create The Baseline Branch

Add Sunwoo's repository as a remote, then copy its `memory-system` branch into a
local branch named `mem-base`:

```bash
cd ~/minitpu/tpu
git remote add sunwoo https://github.com/sunwookim028/mininpu.git
git fetch sunwoo memory-system
git switch -c mem-base sunwoo/memory-system
git push -u origin mem-base
```

The benchmark scripts live on the Codex branch. Run them from the Codex checkout
against the `mem-base` checkout to keep Sunwoo's branch untouched.

## Run From Separate Checkouts

This keeps Sunwoo's baseline branch clean. Sunwoo's baseline branch already keeps
its bitstream under `compiler/tpu_deploy/CornellTPU.bit`; the Codex branch uses
`ultra96-v2/output/artifacts/mem_bd.bit`.

Build the Codex bitstream first:

```bash
cd ~/minitpu-codex/tpu
git checkout codex/fix-system-mem-dma-read
git pull --ff-only
make mem-bitstream
```

Then run the same benchmark payload against each checkout:

```bash
cd ~/minitpu-codex/tpu

bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu-mem-base \
  --variant mem-base \
  --board-ip 132.236.59.72 \
  --out results/mem-base.json

bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu-codex/tpu \
  --variant codex-system-mem-fixed \
  --board-ip 132.236.59.72 \
  --out results/codex-system-mem-fixed.json

python3 benchmarks/compare_mem_benchmarks.py \
  results/mem-base.json \
  results/codex-system-mem-fixed.json
```

If the baseline runtime lacks the async compute/DMA APIs, the double-buffer row
will be marked as skipped for that design. That is still useful: it shows the
feature is not exposed in the older system, while the raw DMA and copy numbers
remain comparable.

The `mem-base` runtime can still run the VADD compute benchmark through
`compiler/tpu_deploy/host.py`, so the compare script reports a measured
non-banked VADD time against the Codex branch's banked-L1 VADD time. The
baseline compute row is single-shot because the legacy RTL does not reset its PC
between repeated `COMPUTE` launches.

For `mem-base`, the runner auto-detects:

- runtime: `compiler/tpu_deploy/host.py`
- bitstream: `compiler/tpu_deploy/CornellTPU.bit`
- hwh: `compiler/tpu_deploy/CornellTPU.hwh`

## Useful Options

Short smoke run:

```bash
bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu-codex/tpu \
  --variant smoke \
  --board-ip 132.236.59.72 \
  --bench-args "--repeats 1 --warmups 0 --sizes 256,1024 --copy-sizes 256,1024"
```

Longer run:

```bash
bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu-codex/tpu \
  --variant fixed-long \
  --board-ip 132.236.59.72 \
  --bench-args "--repeats 10 --warmups 2"
```

Banking-focused run with a larger VADD:

```bash
bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu-mem-base \
  --variant mem-base-vadd2048 \
  --board-ip 132.236.59.72 \
  --out results/mem-base-vadd2048.json \
  --bench-args "--repeats 5 --warmups 1 --vadd-len 2048 --vadd-repeats 128"

bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu-codex/tpu \
  --variant codex-system-mem-fixed-vadd2048 \
  --board-ip 132.236.59.72 \
  --out results/codex-system-mem-fixed-vadd2048.json \
  --bench-args "--repeats 5 --warmups 1 --vadd-len 2048 --vadd-repeats 128"

python3 benchmarks/compare_mem_benchmarks.py \
  results/mem-base-vadd2048.json \
  results/codex-system-mem-fixed-vadd2048.json
```

Strength-focused run. This keeps VADD large and uses larger DMA transfers to
make the optimized host path and double-buffering easier to see. The current
design also reports the 248-element banked VPU row; use the focused run below
for the direct legacy scalar VPU comparison:

```bash
bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu-mem-base \
  --variant mem-base-strength \
  --board-ip 132.236.59.72 \
  --out results/mem-base-strength.json \
  --bench-args "--repeats 5 --warmups 1 --sizes 1024,4096,8192 --copy-sizes 1024,2048,4096 --vadd-len 2048 --vadd-repeats 128 --vpu-elems 248 --dma-words 8192"

bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu/tpu \
  --variant codex-system-mem-strength \
  --board-ip 132.236.59.72 \
  --out results/codex-system-mem-strength.json \
  --bench-args "--repeats 5 --warmups 1 --sizes 1024,4096,8192 --copy-sizes 1024,2048,4096 --vadd-len 2048 --vadd-repeats 128 --vpu-elems 248 --dma-words 8192"

python3 benchmarks/compare_mem_benchmarks.py \
  results/mem-base-strength.json \
  results/codex-system-mem-strength.json
```

Banked VPU head-to-head. The legacy baseline can only run one compute program
per FPGA program, so use this focused mode when you want the direct scalar VPU
versus 8-lane banked VPU result:

```bash
bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu-mem-base \
  --variant mem-base-banked-vpu \
  --board-ip 132.236.59.72 \
  --out results/mem-base-banked-vpu.json \
  --bench-args "--banked-vpu-only --repeats 5 --warmups 1 --vpu-elems 248"

bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu/tpu \
  --variant codex-system-mem-banked-vpu \
  --board-ip 132.236.59.72 \
  --out results/codex-system-mem-banked-vpu.json \
  --bench-args "--banked-vpu-only --repeats 5 --warmups 1 --vpu-elems 248"

python3 benchmarks/compare_mem_benchmarks.py \
  results/mem-base-banked-vpu.json \
  results/codex-system-mem-banked-vpu.json
```
