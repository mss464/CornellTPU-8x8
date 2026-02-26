#!/usr/bin/env python3
"""
Board-level smoke test for Mini-TPU.

Tests:
  1. Connect to FPGA (must be pre-programmed)
  2. Write 16x DEADBEEF to device memory at addr 0 (mode WRITE_DEVMEM=1)
  3. Read back and verify bit-exact match    (mode READ_DEVMEM=2)

Usage: invoked via `make smoke-board` from tpu/
Deployment: board-test copies runtime/pynq_host.py to ~/tpu_deploy/runtime/
            so import directly from runtime.pynq_host, not via runtime.tuda.
"""

import sys
import numpy as np
from runtime.pynq_host import TpuDriver

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


def main():
    print("Board smoke test starting...")
    tpu = TpuDriver(program=False)

    # Build 16-word DEADBEEF pattern.
    # View as float32 so write_bram accepts it; compare as uint32 to avoid NaN equality.
    pattern_u32 = np.array([0xDEADBEEF] * 16, dtype=np.uint32)
    pattern_f32 = pattern_u32.view(np.float32)

    # Write to device memory at addr 0
    tpu.write_bram(0, pattern_f32)

    # Read back from device memory at addr 0
    result_f32 = tpu.read_bram(0, 16)
    result_u32 = result_f32.view(np.uint32)

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
    main()
