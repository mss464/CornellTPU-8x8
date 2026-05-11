#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Run the memory benchmark against an arbitrary MiniTPU checkout.

Required:
  --checkout PATH       Path to the checkout's tpu/ directory
  --variant NAME        Label written into the JSON result

Common options:
  --board-ip IP         Board IP address
  --out FILE            Local JSON output path
  --bit FILE            Bitstream path (auto-detected if omitted)
  --hwh FILE            HWH path (auto-detected if omitted)
  --runtime DIR         Runtime dir (auto-detected if omitted)
  --bench-args ARGS     Extra args passed to mem_benchmark.py

Environment:
  BOARD_USER=xilinx BOARD_PASS=xilinx DEPLOY_DIR=/home/xilinx/minitpu_deploy
USAGE
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKOUT=""
VARIANT=""
BOARD_IP="${BOARD_IP:-}"
BOARD_USER="${BOARD_USER:-xilinx}"
BOARD_PASS="${BOARD_PASS:-xilinx}"
DEPLOY_DIR="${DEPLOY_DIR:-/home/xilinx/minitpu_deploy}"
BIT=""
HWH=""
RUNTIME_DIR=""
OUT=""
BENCH_ARGS=""
LATENCY="${LATENCY:-0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --checkout) CHECKOUT="$2"; shift 2 ;;
    --variant) VARIANT="$2"; shift 2 ;;
    --board-ip) BOARD_IP="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --bit) BIT="$2"; shift 2 ;;
    --hwh) HWH="$2"; shift 2 ;;
    --runtime) RUNTIME_DIR="$2"; shift 2 ;;
    --bench-args) BENCH_ARGS="$2"; shift 2 ;;
    --latency) LATENCY="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$CHECKOUT" || -z "$VARIANT" || -z "$BOARD_IP" ]]; then
  usage >&2
  exit 2
fi

CHECKOUT="$(cd "$CHECKOUT" && pwd)"
if [[ -z "$BIT" ]]; then
  if [[ -f "$CHECKOUT/ultra96-v2/output/artifacts/mem_bd.bit" ]]; then
    BIT="$CHECKOUT/ultra96-v2/output/artifacts/mem_bd.bit"
  elif [[ -f "$CHECKOUT/compiler/tpu_deploy/CornellTPU.bit" ]]; then
    BIT="$CHECKOUT/compiler/tpu_deploy/CornellTPU.bit"
  fi
fi
if [[ -z "$HWH" ]]; then
  if [[ -f "$CHECKOUT/ultra96-v2/output/artifacts/mem_bd.hwh" ]]; then
    HWH="$CHECKOUT/ultra96-v2/output/artifacts/mem_bd.hwh"
  elif [[ -f "$CHECKOUT/compiler/tpu_deploy/CornellTPU.hwh" ]]; then
    HWH="$CHECKOUT/compiler/tpu_deploy/CornellTPU.hwh"
  fi
fi
if [[ -z "$RUNTIME_DIR" ]]; then
  if [[ -d "$CHECKOUT/runtime" ]]; then
    RUNTIME_DIR="$CHECKOUT/runtime"
  elif [[ -d "$CHECKOUT/compiler/tpu_deploy" ]]; then
    RUNTIME_DIR="$CHECKOUT/compiler/tpu_deploy"
  fi
fi
OUT="${OUT:-$PWD/${VARIANT}.mem_bench.json}"

for required in ssh scp sshpass; do
  command -v "$required" >/dev/null 2>&1 || {
    echo "Missing required tool: $required" >&2
    exit 2
  }
done

[[ -f "$BIT" ]] || { echo "Missing bitstream: $BIT" >&2; exit 2; }
[[ -f "$HWH" ]] || { echo "Missing HWH: $HWH" >&2; exit 2; }
[[ -d "$RUNTIME_DIR" ]] || { echo "Missing runtime dir: $RUNTIME_DIR" >&2; exit 2; }

TMP="$(mktemp -d /tmp/tpu_mem_bench.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/runtime" "$TMP/benchmarks" "$TMP/results"
cp -r "$RUNTIME_DIR"/. "$TMP/runtime/"
cp "$SCRIPT_DIR/mem_benchmark.py" "$TMP/benchmarks/"
cp "$BIT" "$TMP/mem_bd.bit"
cp "$HWH" "$TMP/mem_bd.hwh"

REMOTE_JSON="${VARIANT}.mem_bench.json"
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

sshpass -p "$BOARD_PASS" ssh $SSH_OPTS "$BOARD_USER@$BOARD_IP" "mkdir -p '$DEPLOY_DIR'"
sshpass -p "$BOARD_PASS" scp -r $SSH_OPTS "$TMP"/* "$BOARD_USER@$BOARD_IP:$DEPLOY_DIR/"

echo "== Running memory benchmark: $VARIANT =="
sshpass -p "$BOARD_PASS" ssh -t $SSH_OPTS "$BOARD_USER@$BOARD_IP" \
  "cd '$DEPLOY_DIR' && echo '$BOARD_PASS' | sudo -S python3 benchmarks/mem_benchmark.py --bitstream mem_bd.bit --program --latency '$LATENCY' --variant '$VARIANT' --json-out 'results/$REMOTE_JSON' $BENCH_ARGS"

mkdir -p "$(dirname "$OUT")"
sshpass -p "$BOARD_PASS" scp $SSH_OPTS "$BOARD_USER@$BOARD_IP:$DEPLOY_DIR/results/$REMOTE_JSON" "$OUT"
echo "Wrote $OUT"
