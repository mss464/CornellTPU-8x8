#!/usr/bin/env python3
"""
Minimal Debug Read/Write Test for Mini-TPU FPGA

Performs simple write-then-read cycles and prints ALL returned data
to help diagnose data integrity issues.
"""
import argparse
import sys
import time
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


def main():
    parser = argparse.ArgumentParser(description="TPU Debug R/W Test")
    parser.add_argument("bitstream", help="Path to the .bit file")
    args = parser.parse_args()

    tpu = TpuDriver(bitstream=args.bitstream, program=True)

    print("\n" + "=" * 60)
    print("TEST A: Write 8 floats, read 8 floats (single beat)")
    print("=" * 60)
    pattern_a = np.array([10, 20, 30, 40, 50, 60, 70, 80], dtype=np.float32)
    print(f"  Writing: {pattern_a}")
    tpu.write_bram(0, pattern_a)
    time.sleep(0.1)
    result_a = tpu.read_bram(0, 8)
    print(f"  Read:    {result_a}")
    print(f"  Match:   {np.array_equal(result_a, pattern_a)}")

    print("\n" + "=" * 60)
    print("TEST B: Write DIFFERENT 8 floats to SAME addr, read back")
    print("=" * 60)
    pattern_b = np.array([1, 2, 3, 4, 5, 6, 7, 8], dtype=np.float32)
    print(f"  Writing: {pattern_b}")
    tpu.write_bram(0, pattern_b)
    time.sleep(0.1)
    result_b = tpu.read_bram(0, 8)
    print(f"  Read:    {result_b}")
    print(f"  Match:   {np.array_equal(result_b, pattern_b)}")
    if np.array_equal(result_b, pattern_a):
        print("  >>> STALE: Got Test A data — write did NOT overwrite!")
    elif np.array_equal(result_b, pattern_b):
        print("  >>> FRESH: Overwrite successful!")
    else:
        print(f"  >>> UNEXPECTED data")

    print("\n" + "=" * 60)
    print("TEST C: Write 16 floats (2 beats), read back ALL 16")
    print("=" * 60)
    pattern_c = np.arange(16, dtype=np.float32) + 100
    print(f"  Writing: {pattern_c}")
    tpu.write_bram(0, pattern_c)
    time.sleep(0.1)
    result_c = tpu.read_bram(0, 16)
    print(f"  Read:    {result_c}")
    print(f"  Match:   {np.array_equal(result_c, pattern_c)}")
    print(f"  Beat 0 (elems 0-7):  expected={pattern_c[:8]}, got={result_c[:8]}")
    print(f"  Beat 1 (elems 8-15): expected={pattern_c[8:]}, got={result_c[8:]}")

    print("\n" + "=" * 60)
    print("TEST D: Write 64 floats (8 beats), read back, show per-beat")
    print("=" * 60)
    pattern_d = np.arange(64, dtype=np.float32)
    print(f"  Writing 64 sequential floats [0..63]")
    tpu.write_bram(0, pattern_d)
    time.sleep(0.1)
    result_d = tpu.read_bram(0, 64)
    for beat in range(8):
        s = beat * 8
        e = s + 8
        match = np.array_equal(result_d[s:e], pattern_d[s:e])
        print(f"  Beat {beat} [{s:2d}-{e-1:2d}]: exp={pattern_d[s:e]}  got={result_d[s:e]}  {'OK' if match else 'MISMATCH!'}")

    print("\n" + "=" * 60)
    print("TEST E: Read-after-write consistency (write new, read immediately)")
    print("=" * 60)
    pattern_e = np.array([99, 88, 77, 66, 55, 44, 33, 22], dtype=np.float32)
    print(f"  Writing: {pattern_e}")
    tpu.write_bram(0, pattern_e)
    time.sleep(0.1)
    result_e = tpu.read_bram(0, 8)
    print(f"  Read:    {result_e}")
    print(f"  Match:   {np.array_equal(result_e, pattern_e)}")

    print("\n" + "=" * 60)
    all_pass = (
        np.array_equal(result_a, pattern_a)
        and np.array_equal(result_b, pattern_b)
        and np.array_equal(result_c, pattern_c)
        and np.array_equal(result_d, pattern_d)
        and np.array_equal(result_e, pattern_e)
    )
    if all_pass:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED — see per-beat detail above")
    print("=" * 60)


if __name__ == "__main__":
    main()
