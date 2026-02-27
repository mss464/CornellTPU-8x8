#!/usr/bin/env python3
"""
board_tests/test_board.py — Mini-TPU manual offline board test suite.

Run directly on the PYNQ board (or any host with PYNQ + programmed FPGA):

  cd /home/xilinx/tpu_deploy
  python3 board_tests/test_board.py [--test <name>] [--verbose] [--program]

Tests are ordered from simple to complex. Each test is self-contained and
prints PASS/FAIL. A test that fails will not block subsequent tests.

Tests:
  1.  devmem_rw_small      — 8-word write/read roundtrip at addr 0
  2.  devmem_rw_large      — 256-word write/read roundtrip at addr 0
  3.  devmem_base_offset   — write at addr 512, read back from same offset
  4.  devmem_multi_region  — two independent regions; verify no aliasing
  5.  devmem_boundary_8    — 8 words (= FIFO depth); catch Bug A/B regressions
  6.  devmem_boundary_9    — 9 words (FIFO+1); drain transition test
  7.  devmem_known_values  — write pattern [1.0, -1.0, 0.5, …]; bit-exact compare
  8.  l2_dm_roundtrip      — write DevMem, copy to L2, copy back, verify
  9.  l2_l1_roundtrip      — write DevMem→L2→L1→L2→DevMem, verify
  10. hierarchy_pipeline   — full DevMem→L2→L1→[identity kernel]→L1→L2→DevMem
  11. vadd_kernel           — VADD kernel: C[i] = A[i] + B[i], verify 8 elements
  12. deadbeef              — write 0xDEADBEEF pattern as float32, verify bit-exact

Usage:
  python3 test_board.py                   # run all tests
  python3 test_board.py --test devmem_rw_small
  python3 test_board.py --verbose          # show per-element mismatches
  python3 test_board.py --program          # re-flash bitstream before running
"""

import argparse
import sys
import os
import struct
import time
import numpy as np

# Allow import from parent directory (where pynq_host.py lives)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pynq_host import TpuDriver


# ---------------------------------------------------------------------------
# Instruction encoding helpers (mirrors test_tpu_compute.py)
# ---------------------------------------------------------------------------
HALT_INSTR = np.uint64(3 << 62)  # mode=3 (HALT)


def encode_vpu_instr(addr_a=0, addr_b=0, addr_out=0, vpu_type=0,
                     vreg_dst=0, vreg_a=0, vreg_b=0, vpu_opcode=0, scalar_b=0):
    """Encode a VPU instruction (mode=0, decoder.sv field layout)."""
    instr = np.uint64(0)
    instr |= np.uint64(0 & 0x3) << np.uint64(62)
    instr |= np.uint64(addr_a   & 0x1FFF) << np.uint64(49)
    instr |= np.uint64(addr_b   & 0x1FFF) << np.uint64(36)
    instr |= np.uint64(addr_out & 0x1FFF) << np.uint64(23)
    instr |= np.uint64(vpu_type & 0x7)    << np.uint64(20)
    instr |= np.uint64(vreg_dst & 0x7)    << np.uint64(17)
    instr |= np.uint64(vreg_a   & 0x7)    << np.uint64(14)
    instr |= np.uint64(vreg_b   & 0x7)    << np.uint64(11)
    instr |= np.uint64(vpu_opcode & 0x7)  << np.uint64(4)
    instr |= np.uint64(scalar_b & 0x1)    << np.uint64(3)
    return instr


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------
class TestSuite:
    def __init__(self, tpu: TpuDriver, verbose: bool = False):
        self.tpu     = tpu
        self.verbose = verbose
        self.passed  = 0
        self.failed  = 0
        self.skipped = 0
        self._results = []  # (name, status, detail)

    def record(self, name, passed, detail=""):
        if passed:
            print(f"  PASS: {name}")
            self.passed += 1
            self._results.append((name, "PASS", detail))
        else:
            print(f"  FAIL: {name}" + (f"  — {detail}" if detail else ""))
            self.failed += 1
            self._results.append((name, "FAIL", detail))

    def skip(self, name, reason=""):
        print(f"  SKIP: {name}" + (f"  — {reason}" if reason else ""))
        self.skipped += 1
        self._results.append((name, "SKIP", reason))

    def summary(self):
        total = self.passed + self.failed + self.skipped
        print()
        print("=" * 60)
        print(f"BOARD TEST: {self.passed}/{total} passed"
              + (f", {self.skipped} skipped" if self.skipped else ""))
        if self.failed > 0:
            print("FAILED tests:")
            for name, status, detail in self._results:
                if status == "FAIL":
                    print(f"  - {name}" + (f": {detail}" if detail else ""))
        print("=" * 60)
        return self.failed == 0

    def _compare(self, result, expected, name):
        """Compare float32 arrays; return (passed, detail_str)."""
        if len(result) != len(expected):
            return False, f"length mismatch: got {len(result)}, expected {len(expected)}"
        mismatches = []
        for i, (r, e) in enumerate(zip(result, expected)):
            if abs(float(r) - float(e)) > 1e-5 * max(1.0, abs(float(e))):
                mismatches.append(f"[{i}]: got {r:.6g}, expected {e:.6g}")
                if not self.verbose and len(mismatches) >= 4:
                    mismatches.append("... (more)")
                    break
        if mismatches:
            return False, "; ".join(mismatches)
        return True, ""

    def _compare_u32(self, result_f32, expected_u32):
        """Bit-exact comparison via uint32 view."""
        result_u32 = np.asarray(result_f32, dtype=np.float32).view(np.uint32)
        expected_u32 = np.asarray(expected_u32, dtype=np.uint32)
        mismatches = []
        for i, (r, e) in enumerate(zip(result_u32, expected_u32)):
            if r != e:
                mismatches.append(f"[{i}]: got 0x{r:08X}, expected 0x{e:08X}")
                if not self.verbose and len(mismatches) >= 4:
                    mismatches.append("... (more)")
                    break
        if mismatches:
            return False, "; ".join(mismatches)
        return True, ""


# ---------------------------------------------------------------------------
# Individual tests
# ---------------------------------------------------------------------------
def test_devmem_rw_small(s: TestSuite):
    n = 8
    pattern = np.arange(n, dtype=np.float32)
    s.tpu.write_bram(0, pattern)
    result = s.tpu.read_bram(0, n)
    ok, detail = s._compare(result, pattern, "devmem_rw_small")
    s.record("devmem_rw_small", ok, detail)


def test_devmem_rw_large(s: TestSuite):
    n = 256
    pattern = np.arange(n, dtype=np.float32)
    s.tpu.write_bram(0, pattern)
    result = s.tpu.read_bram(0, n)
    ok, detail = s._compare(result, pattern, "devmem_rw_large")
    s.record("devmem_rw_large", ok, detail)


def test_devmem_base_offset(s: TestSuite):
    n = 32
    addr = 512
    pattern = np.linspace(0.0, 1.0, n, dtype=np.float32)
    s.tpu.write_bram(addr, pattern)
    result = s.tpu.read_bram(addr, n)
    ok, detail = s._compare(result, pattern, "devmem_base_offset")
    s.record("devmem_base_offset", ok, detail)


def test_devmem_multi_region(s: TestSuite):
    """Write two non-overlapping regions; verify neither aliases the other."""
    n = 16
    a_addr, b_addr = 0, 100
    a_data = np.ones(n, dtype=np.float32) * 1.1
    b_data = np.ones(n, dtype=np.float32) * 2.2
    s.tpu.write_bram(a_addr, a_data)
    s.tpu.write_bram(b_addr, b_data)
    ra = s.tpu.read_bram(a_addr, n)
    rb = s.tpu.read_bram(b_addr, n)
    ok_a, d_a = s._compare(ra, a_data, "multi_region_A")
    ok_b, d_b = s._compare(rb, b_data, "multi_region_B")
    ok = ok_a and ok_b
    detail = (d_a + " | " + d_b).strip(" | ")
    s.record("devmem_multi_region", ok, detail)


def test_devmem_boundary_8(s: TestSuite):
    """N=8 = FIFO depth. Regression for Bug A (first element loss) and Bug B (duplicate)."""
    n = 8
    pattern = np.arange(n, dtype=np.float32)
    s.tpu.write_bram(0, pattern)
    result = s.tpu.read_bram(0, n)
    # Bug A check: first element must be 0.0
    if abs(result[0] - 0.0) > 1e-6:
        s.record("devmem_boundary_8", False, f"Bug A: result[0]={result[0]:.4g} != 0.0")
        return
    # Bug B check: no adjacent duplicates
    for i in range(n - 1):
        if abs(result[i] - result[i + 1]) < 1e-9 and abs(result[i]) > 1e-9:
            s.record("devmem_boundary_8", False,
                     f"Bug B: duplicate at [{i}]/[{i+1}]={result[i]:.4g}")
            return
    ok, detail = s._compare(result, pattern, "devmem_boundary_8")
    s.record("devmem_boundary_8", ok, detail)


def test_devmem_boundary_9(s: TestSuite):
    """N=9 = FIFO+1. Tests prefill-to-steady-state transition."""
    n = 9
    pattern = np.arange(n, dtype=np.float32)
    s.tpu.write_bram(0, pattern)
    result = s.tpu.read_bram(0, n)
    ok, detail = s._compare(result, pattern, "devmem_boundary_9")
    s.record("devmem_boundary_9", ok, detail)


def test_devmem_known_values(s: TestSuite):
    """Bit-exact pattern with edge values: positive, negative, half, tiny."""
    pattern_f32 = np.array([1.0, -1.0, 0.5, -0.5, 2.0, 4.0, 8.0, 16.0], dtype=np.float32)
    pattern_u32 = pattern_f32.view(np.uint32)
    s.tpu.write_bram(0, pattern_f32)
    result_f32 = s.tpu.read_bram(0, len(pattern_f32))
    ok, detail = s._compare_u32(result_f32, pattern_u32)
    s.record("devmem_known_values", ok, detail)


def test_deadbeef(s: TestSuite):
    """Classic DEADBEEF bit-exact roundtrip (original smoke-board test)."""
    n = 16
    pattern_u32 = np.array([0xDEADBEEF] * n, dtype=np.uint32)
    pattern_f32 = pattern_u32.view(np.float32)
    s.tpu.write_bram(0, pattern_f32)
    result_f32 = s.tpu.read_bram(0, n)
    ok, detail = s._compare_u32(result_f32, pattern_u32)
    s.record("deadbeef", ok, detail)


def test_l2_dm_roundtrip(s: TestSuite):
    """DevMem[0:16] → L2[0:16] → DevMem[200:215], verify."""
    n = 16
    pattern = np.arange(n, dtype=np.float32) * 3.14
    s.tpu.write_bram(0, pattern)
    s.tpu.devmem_to_l2(devmem_addr=0, l2_addr=0, length=n)
    s.tpu.l2_to_devmem(l2_addr=0, devmem_addr=200, length=n)
    result = s.tpu.read_bram(200, n)
    ok, detail = s._compare(result, pattern, "l2_dm_roundtrip")
    s.record("l2_dm_roundtrip", ok, detail)


def test_l2_l1_roundtrip(s: TestSuite):
    """Full DevMem→L2→L1→L2→DevMem pipeline with 8 words."""
    n = 8
    pattern = np.array([float(i * 7 + 3) for i in range(n)], dtype=np.float32)
    s.tpu.write_bram(0, pattern)
    s.tpu.devmem_to_l2(devmem_addr=0, l2_addr=0, length=n)
    s.tpu.l2_to_l1(l2_addr=0, l1_base_addr=0, length=n)
    s.tpu.l1_to_l2(l1_base_addr=0, l2_addr=64, length=n)
    s.tpu.l2_to_devmem(l2_addr=64, devmem_addr=300, length=n)
    result = s.tpu.read_bram(300, n)
    ok, detail = s._compare(result, pattern, "l2_l1_roundtrip")
    s.record("l2_l1_roundtrip", ok, detail)


def test_hierarchy_pipeline(s: TestSuite):
    """Full hierarchy: DevMem→L2→L1→[identity kernel]→L1→L2→DevMem.

    Identity kernel: vload(V0, addr=0), vstore(V0, addr=8), halt.
    Verifies that compute tile correctly reads L1 data written by L2 ctrl.
    """
    n = 8
    input_data = np.array([float(i + 1) for i in range(n)], dtype=np.float32)

    # Stage data into L1[0:7]
    s.tpu.write_bram(0, input_data)
    s.tpu.devmem_to_l2(devmem_addr=0, l2_addr=0, length=n)
    s.tpu.l2_to_l1(l2_addr=0, l1_base_addr=0, length=n)

    # Load identity kernel
    vload  = encode_vpu_instr(addr_a=0,   vpu_type=1, vreg_dst=0)
    vstore = encode_vpu_instr(addr_out=8, vpu_type=2, vreg_a=0)
    s.tpu.write_instructions(np.array([vload, vstore, HALT_INSTR], dtype=np.uint64))

    # Execute
    s.tpu.compute(timeout=30.0)

    # Read result via L1[8:15] → L2 → DevMem
    s.tpu.l1_to_l2(l1_base_addr=8, l2_addr=8, length=n)
    s.tpu.l2_to_devmem(l2_addr=8, devmem_addr=400, length=n)
    result = s.tpu.read_bram(400, n)

    ok, detail = s._compare(result, input_data, "hierarchy_pipeline")
    s.record("hierarchy_pipeline", ok, detail)


def test_vadd_kernel(s: TestSuite):
    """VADD kernel: C[i] = A[i] + B[i] for 8 elements.

    Tests VLOAD, VCOMPUTE (opcode=0 ADD), VSTORE path end-to-end on hardware.
    """
    n = 8
    a = np.array([float(i + 1) for i in range(n)], dtype=np.float32)   # [1..8]
    b = np.array([float(i * 2 + 10) for i in range(n)], dtype=np.float32)  # [10,12..24]
    expected = a + b

    # Load A into L1[0:7], B into L1[8:15]
    s.tpu.write_bram(0, a)
    s.tpu.devmem_to_l2(devmem_addr=0, l2_addr=0, length=n)
    s.tpu.l2_to_l1(l2_addr=0, l1_base_addr=0, length=n)

    s.tpu.write_bram(8, b)
    s.tpu.devmem_to_l2(devmem_addr=8, l2_addr=8, length=n)
    s.tpu.l2_to_l1(l2_addr=8, l1_base_addr=8, length=n)

    # VADD kernel
    vload0  = encode_vpu_instr(addr_a=0,   vpu_type=1, vreg_dst=0)
    vload1  = encode_vpu_instr(addr_a=8,   vpu_type=1, vreg_dst=1)
    vadd    = encode_vpu_instr(vpu_type=3, vreg_dst=2, vreg_a=0, vreg_b=1, vpu_opcode=0)
    vstore2 = encode_vpu_instr(addr_out=16, vpu_type=2, vreg_a=2)
    s.tpu.write_instructions(np.array([vload0, vload1, vadd, vstore2, HALT_INSTR],
                                      dtype=np.uint64))
    s.tpu.compute(timeout=30.0)

    # Read result
    s.tpu.l1_to_l2(l1_base_addr=16, l2_addr=16, length=n)
    s.tpu.l2_to_devmem(l2_addr=16, devmem_addr=500, length=n)
    result = s.tpu.read_bram(500, n)

    ok, detail = s._compare(result, expected, "vadd_kernel")
    s.record("vadd_kernel", ok, detail)


# ---------------------------------------------------------------------------
# Test registry — ordered simple → complex
# ---------------------------------------------------------------------------
ALL_TESTS = [
    ("devmem_rw_small",     test_devmem_rw_small),
    ("devmem_rw_large",     test_devmem_rw_large),
    ("devmem_base_offset",  test_devmem_base_offset),
    ("devmem_multi_region", test_devmem_multi_region),
    ("devmem_boundary_8",   test_devmem_boundary_8),
    ("devmem_boundary_9",   test_devmem_boundary_9),
    ("devmem_known_values", test_devmem_known_values),
    ("deadbeef",            test_deadbeef),
    ("l2_dm_roundtrip",     test_l2_dm_roundtrip),
    ("l2_l1_roundtrip",     test_l2_l1_roundtrip),
    ("hierarchy_pipeline",  test_hierarchy_pipeline),
    ("vadd_kernel",         test_vadd_kernel),
]


def main():
    parser = argparse.ArgumentParser(description="Mini-TPU board test suite")
    parser.add_argument("--test",    metavar="NAME",
                        help="Run only this test (partial name match OK)")
    parser.add_argument("--verbose", action="store_true",
                        help="Show all mismatches, not just first 4")
    parser.add_argument("--program", action="store_true",
                        help="Re-flash FPGA bitstream before running tests")
    parser.add_argument("--list",    action="store_true",
                        help="List all test names and exit")
    args = parser.parse_args()

    if args.list:
        for name, _ in ALL_TESTS:
            print(f"  {name}")
        return

    print("Mini-TPU Board Test Suite")
    print(f"  Connecting to hardware (program={args.program})...")
    try:
        tpu = TpuDriver(program=args.program)
    except Exception as e:
        print(f"FATAL: Could not connect to TPU hardware: {e}")
        sys.exit(2)

    suite = TestSuite(tpu, verbose=args.verbose)

    # Filter tests
    tests_to_run = ALL_TESTS
    if args.test:
        tests_to_run = [(n, fn) for n, fn in ALL_TESTS if args.test in n]
        if not tests_to_run:
            print(f"No test matching '{args.test}'. Use --list to see all tests.")
            sys.exit(1)

    print(f"  Running {len(tests_to_run)} test(s)...")
    print()

    for name, fn in tests_to_run:
        try:
            fn(suite)
        except TimeoutError as e:
            suite.record(name, False, f"TimeoutError: {e}")
        except Exception as e:
            suite.record(name, False, f"Exception: {type(e).__name__}: {e}")

    passed = suite.summary()
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
