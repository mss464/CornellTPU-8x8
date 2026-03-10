#!/usr/bin/env python3
"""
Data Integrity Test for Mini-TPU FPGA

Verifies the AXI-Stream slave data shift bug fix by writing known patterns
to BRAM and reading them back. The bug caused data[N] to be written to
addr[N+1], with garbage at addr[0].

Usage:
    python3 test_data_integrity.py <bitstream.bit>
"""

import argparse
import sys
import time
import os
import numpy as np

try:
    from runtime.pynq_host import TpuDriver
except ImportError:
    try:
        from hal.pynq_host import TpuDriver
    except ImportError:
        try:
             from pynq_host import TpuDriver
        except ImportError:
            print("ERROR: Could not import TpuDriver")
            sys.exit(1)


def test_sequential_pattern(tpu, base_addr, size):
    """Write sequential [0, 1, 2, ..., N-1] and verify."""
    pattern = np.arange(size, dtype=np.float32)
    tpu.write_bram(base_addr, pattern)
    result = tpu.read_bram(base_addr, size)

    # Check first element specifically (this was garbage with the bug)
    if result[0] != 0.0:
        print(f"  FAIL: First element = {result[0]}, expected 0.0")
        return False

    # Check all elements
    if not np.array_equal(result, pattern):
        mismatches = np.where(result != pattern)[0]
        print(f"  FAIL: {len(mismatches)} mismatches at indices {mismatches[:5]}...")
        print(f"    Expected: {pattern[:8]}...")
        print(f"    Got:      {result[:8]}...")
        return False

    print(f"  PASS: {size} elements at addr {base_addr}")
    return True


def test_known_values(tpu, base_addr):
    """Write specific float values and verify exact match."""
    # Use values that are exactly representable in FP32
    pattern = np.array([1.0, -1.0, 0.5, -0.5, 2.0, 4.0, 8.0, 16.0], dtype=np.float32)
    tpu.write_bram(base_addr, pattern)
    result = tpu.read_bram(base_addr, len(pattern))

    if not np.array_equal(result, pattern):
        print(f"  FAIL: Known values mismatch")
        print(f"    Expected: {pattern}")
        print(f"    Got:      {result}")
        return False

    print(f"  PASS: Known values at addr {base_addr}")
    return True


def test_burst_boundaries(tpu):
    """Test various transfer sizes including edge cases."""
    import gc
    sizes = [1, 4, 8, 15, 16, 17, 32, 64]
    all_pass = True

    for size in sizes:
        gc.collect()  # Force CMA buffer release before next allocation
        time.sleep(0.05)  # Allow DMA/CMA to settle between iterations
        pattern = np.arange(size, dtype=np.float32) + 100  # Offset to distinguish from addr
        tpu.write_bram(0, pattern)
        result = tpu.read_bram(0, size)

        if not np.array_equal(result, pattern):
            print(f"  FAIL: Size {size} - first elem {result[0]}, expected {pattern[0]}")
            all_pass = False
        else:
            print(f"  PASS: Size {size}")

    return all_pass


def main():
    parser = argparse.ArgumentParser(description="TPU Data Integrity Test")
    parser.add_argument("bitstream", help="Path to the .bit file to program")
    args = parser.parse_args()

    # Initialize TPU and program FPGA
    tpu = TpuDriver(bitstream=args.bitstream, program=True)

    all_passed = True

    print("\n=== Test 1: Sequential Pattern (16 elements) ===")
    if not test_sequential_pattern(tpu, 0, 16):
        all_passed = False

    print("\n=== Test 2: Sequential Pattern (64 elements) ===")
    if not test_sequential_pattern(tpu, 0, 64):
        all_passed = False

    print("\n=== Test 3: Known Float Values ===")
    if not test_known_values(tpu, 0):
        all_passed = False

    print("\n=== Test 4: Burst Size Boundaries ===")
    if not test_burst_boundaries(tpu):
        all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("ALL TESTS PASSED - Data shift bug fix verified!")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED - Bug may still be present")
        sys.exit(1)


if __name__ == "__main__":
    main()
