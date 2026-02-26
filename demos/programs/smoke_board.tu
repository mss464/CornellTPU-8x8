#!/usr/bin/env python3
"""
Board-level smoke test for Mini-TPU.

Tests:
  1. tudaInit() — program FPGA
  2. Write 16x DEADBEEF to device memory at addr 0
  3. Read back and verify bit-exact match

Usage: invoked via `make smoke-board` from tpu/
"""

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.tuda import host, tudaInit, tudaMemcpy

PASS = 0
FAIL = 0


def record(name, passed):
    global PASS, FAIL
    if passed:
        print(f"PASS: {name}")
        PASS += 1
    else:
        print(f"FAIL: {name}")
        FAIL += 1


@host
def run_board_smoke():
    print("Board smoke test starting...")
    tudaInit()

    # Build 16-word DEADBEEF pattern (reinterpret uint32 bits as float32)
    pattern = np.array([0xDEADBEEF] * 16, dtype=np.uint32).view(np.float32)

    # Write to device memory at addr 0 (HostToDevice = mode 1)
    tudaMemcpy(0, pattern, "HostToDevice")

    # Read back from device memory at addr 0 (DeviceToHost = mode 2)
    result = tudaMemcpy(0, 16, "DeviceToHost")

    # Compare bit-exact (view as uint32 to avoid float NaN equality issues)
    result_u32 = result.view(np.uint32)
    pattern_u32 = pattern.view(np.uint32)
    passed = bool(np.all(result_u32 == pattern_u32))

    record("devmem_roundtrip", passed)

    if not passed:
        for i, (r, p) in enumerate(zip(result_u32, pattern_u32)):
            if r != p:
                print(f"  Mismatch at [{i}]: expected 0x{p:08X}, got 0x{r:08X}")

    total = PASS + FAIL
    print(f"\nSMOKE BOARD: {PASS}/{total} passed")
    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_board_smoke()
