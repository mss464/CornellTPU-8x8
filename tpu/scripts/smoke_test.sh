#!/usr/bin/env bash
# smoke_test.sh — Mini-TPU smoke test runner
#
# Usage: smoke_test.sh [--sim | --sim-full | --board]
#   --sim       Fast: 3 system tests (data_integrity, device_mem, l2_tile)
#   --sim-full  Full: system tests + compute unit tests + compiler smoke
#   --board     Board: program FPGA + DEADBEEF roundtrip
# Exit: 0 if all pass, 1 if any fail
# Output: one line per test: "PASS: <name>" or "FAIL: <name>", plus final summary

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TPU_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$TPU_DIR/.." && pwd)"

SYS_DIR="$TPU_DIR/verification/system"
UNIT_DIR="$TPU_DIR/verification/compute_tile"
COMPILER_DIR="$PROJECT_ROOT/compiler/verification"

PASS=0
FAIL=0

run_sim_test() {
    local name="$1"
    local dir="$2"
    local target="$3"
    local log="/tmp/tpu_smoke_${name}.log"

    if make -C "$dir" "$target" > "$log" 2>&1; then
        local xml="$dir/results.xml"
        if [ -f "$xml" ] && grep -q -E '<failure|<error' "$xml"; then
            echo "FAIL: $name (see $log)"
            FAIL=$((FAIL + 1))
        else
            echo "PASS: $name"
            PASS=$((PASS + 1))
        fi
    else
        echo "FAIL: $name (see $log)"
        FAIL=$((FAIL + 1))
    fi
}

MODE="${1:---sim}"

case "$MODE" in
    --sim)
        run_sim_test "data_integrity" "$SYS_DIR" "test_data_integrity_rtl"
        run_sim_test "device_mem"     "$SYS_DIR" "test_device_mem"
        run_sim_test "l2_tile"        "$SYS_DIR" "test_l2_tile"
        ;;
    --sim-full)
        run_sim_test "data_integrity" "$SYS_DIR"  "test_data_integrity_rtl"
        run_sim_test "device_mem"     "$SYS_DIR"  "test_device_mem"
        run_sim_test "l2_tile"        "$SYS_DIR"  "test_l2_tile"
        run_sim_test "compute_unit"   "$UNIT_DIR" "test_all"
        if [ -d "$COMPILER_DIR" ]; then
            run_sim_test "compiler_smoke" "$COMPILER_DIR" "smoke-test"
        fi
        ;;
    --board)
        cd "$TPU_DIR"
        make smoke-board
        exit $?
        ;;
    *)
        echo "Usage: $0 [--sim | --sim-full | --board]"
        exit 1
        ;;
esac

TOTAL=$((PASS + FAIL))
echo ""
echo "SMOKE SIM: $PASS/$TOTAL passed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
