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
- overlapped compute plus DMA time, when the runtime exposes independent DMA and compute waits
- an analytical 1-bank vs 8-bank L1 model for wide vector-access speedup

## Create The Baseline Branch

Add Sunwoo's repository as a remote, then copy its `memory-system` branch into a
local branch named `mem-base`:

```bash
cd ~/minitpu/tpu
git remote add sunwoo <SUNWOO_MINITPU_REPO_URL>
git fetch sunwoo memory-system
git switch -c mem-base sunwoo/memory-system
git push -u origin mem-base
```

The benchmark scripts live on the Codex branch. You can either run them from a
separate Codex checkout against `mem-base`, or cherry-pick the benchmark-only
commit onto `mem-base` after it is created.

## Run From Separate Checkouts

This keeps Sunwoo's baseline branch clean. Build each checkout's bitstream first:

```bash
cd ~/minitpu-mem-base/tpu
git checkout mem-base
make mem-bitstream

cd ~/minitpu-codex/tpu
git checkout codex/fix-system-mem-dma-read
git pull --ff-only
make mem-bitstream
```

Then run the same benchmark payload against each checkout:

```bash
cd ~/minitpu-codex/tpu

bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu-mem-base/tpu \
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

## Run By Switching Branches

If you prefer a single checkout, cherry-pick the benchmark commit onto
`mem-base`, build/run, then switch back to the Codex branch and repeat:

```bash
cd ~/minitpu/tpu

git switch mem-base
make mem-bitstream
make mem-benchmark BOARD_IP=132.236.59.72 \
  BENCH_ARGS="--variant mem-base --repeats 5 --warmups 1"

git switch codex/fix-system-mem-dma-read
git pull --ff-only
make mem-bitstream
make mem-benchmark BOARD_IP=132.236.59.72 \
  BENCH_ARGS="--variant codex-system-mem-fixed --repeats 5 --warmups 1"
```

If the baseline runtime lacks the async compute/DMA APIs, the double-buffer row
will be marked as skipped for that design. That is still useful: it shows the
feature is not exposed in the older system, while the raw DMA and copy numbers
remain comparable.

## Useful Options

Short smoke run:

```bash
bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu/tpu \
  --variant smoke \
  --board-ip 132.236.59.72 \
  --bench-args "--repeats 1 --warmups 0 --sizes 256,1024 --copy-sizes 256,1024"
```

Longer run:

```bash
bash benchmarks/run_mem_benchmark_from_checkout.sh \
  --checkout ~/minitpu/tpu \
  --variant fixed-long \
  --board-ip 132.236.59.72 \
  --bench-args "--repeats 10 --warmups 2"
```
