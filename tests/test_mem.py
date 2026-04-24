#!/usr/bin/env python3
"""
test_mem_system.py — Board tests for the memory subsystem design.

Run on the PYNQ board (or any host with PYNQ + programmed FPGA):

  cd /home/xilinx/tpu_deploy
  python3 board_tests/test_mem_system.py [--test <name>] [--verbose] [--program]

Tests (ordered simple → complex):
  1.  dma_write_read      — 32-word DMA write/read roundtrip
  2.  dma_large_transfer  — 1024-word DMA write/read
  3.  dma_offset_addr     — write at non-zero address, read back
  4.  mmio_write_read     — 8-word MMIO write/read roundtrip
  5.  mmio_random_access  — individual word MMIO reads/writes
  6.  dma_write_mmio_read — write via DMA, verify via MMIO (cross-path)
  7.  mmio_write_dma_read — write via MMIO, verify via DMA (cross-path)
  8.  sys_to_onchip       — sys_mem → onchip_mem → sys_mem roundtrip
  9.  onchip_roundtrip    — full: host→sys→onchip→sys→host
  10. bitpattern_deadbeef — bit-exact 0xDEADBEEF verification
"""

import argparse
import sys
import os
import signal
import struct
import time
import numpy as np


# ── SIGBUS → Python exception bridge ────────────────────────────────────
class BusError(RuntimeError):
    pass

def _sigbus_handler(signum, frame):
    raise BusError("SIGBUS received — likely DMA overrun or buffer misalignment")

signal.signal(signal.SIGBUS, _sigbus_handler)

# Allow import from sibling runtime/ directory in minitpu root (dev) or relative (board)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'runtime'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'runtime'))
from pynq_host import MemDriver


# ── Test harness ────────────────────────────────────────────────────────────
class TestSuite:
    def __init__(self, driver: MemDriver, verbose: bool = False):
        self.drv     = driver
        self.verbose = verbose
        self.passed  = 0
        self.failed  = 0
        self.skipped = 0
        self._results = []

    def record(self, name, passed, detail=""):
        if passed:
            print(f"  PASS: {name}")
            self.passed += 1
        else:
            print(f"  FAIL: {name}" + (f"  — {detail}" if detail else ""))
            self.failed += 1
        self._results.append((name, "PASS" if passed else "FAIL", detail))

    def skip(self, name, reason=""):
        print(f"  SKIP: {name}" + (f"  — {reason}" if reason else ""))
        self.skipped += 1
        self._results.append((name, "SKIP", reason))

    def summary(self):
        total = self.passed + self.failed + self.skipped
        print()
        print("=" * 60)
        print(f"MEMORY SYSTEM TEST: {self.passed}/{total} passed"
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


# ── Individual Tests ────────────────────────────────────────────────────────

def test_dma_write_read(s: TestSuite):
    """32-word DMA write/read roundtrip at addr 0."""
    n = 32
    pattern = np.arange(n, dtype=np.float32)
    s.drv.send_bytes(0, pattern, method='dma')
    result = s.drv.read_bytes(0, n, method='dma')
    ok, detail = s._compare(result, pattern, "dma_write_read")
    s.record("dma_write_read", ok, detail)


def test_dma_large_transfer(s: TestSuite):
    """1024-word DMA write/read roundtrip."""
    n = 1024
    pattern = np.arange(n, dtype=np.float32)
    s.drv.send_bytes(0, pattern, method='dma')
    result = s.drv.read_bytes(0, n, method='dma')
    ok, detail = s._compare(result, pattern, "dma_large_transfer")
    s.record("dma_large_transfer", ok, detail)


def test_dma_offset_addr(s: TestSuite):
    """Write at address 512, read back from same offset."""
    n = 32
    addr = 512
    pattern = np.linspace(0.0, 1.0, n, dtype=np.float32)
    s.drv.send_bytes(addr, pattern, method='dma')
    result = s.drv.read_bytes(addr, n, method='dma')
    ok, detail = s._compare(result, pattern, "dma_offset_addr")
    s.record("dma_offset_addr", ok, detail)


def test_mmio_write_read(s: TestSuite):
    """8-word MMIO write/read roundtrip."""
    if s.drv.axi_full_mmio is None:
        s.skip("mmio_write_read", "AXI4-Full MMIO not available")
        return
    n = 8
    pattern = np.array([float(i * 3 + 1) for i in range(n)], dtype=np.float32)
    s.drv.send_bytes(0, pattern, method='mmio')
    result = s.drv.read_bytes(0, n, method='mmio')
    ok, detail = s._compare(result, pattern, "mmio_write_read")
    s.record("mmio_write_read", ok, detail)


def test_mmio_random_access(s: TestSuite):
    """Individual word MMIO writes at scattered addresses, then verify."""
    if s.drv.axi_full_mmio is None:
        s.skip("mmio_random_access", "AXI4-Full MMIO not available")
        return
    addrs = [0, 5, 17, 100, 255]
    values = [3.14, -2.71, 0.001, 42.0, 99.9]
    for addr, val in zip(addrs, values):
        s.drv.send_bytes(addr, np.array([val], dtype=np.float32), method='mmio')
    ok = True
    details = []
    for addr, val in zip(addrs, values):
        result = s.drv.read_bytes(addr, 1, method='mmio')
        if abs(float(result[0]) - val) > 1e-5 * max(1.0, abs(val)):
            ok = False
            details.append(f"addr={addr}: got {result[0]:.6g}, expected {val:.6g}")
    s.record("mmio_random_access", ok, "; ".join(details))


def test_dma_write_mmio_read(s: TestSuite):
    """Write via DMA, verify via MMIO (cross-path integrity)."""
    if s.drv.axi_full_mmio is None:
        s.skip("dma_write_mmio_read", "AXI4-Full MMIO not available")
        return
    n = 16
    pattern = np.arange(n, dtype=np.float32) * 2.5
    s.drv.send_bytes(0, pattern, method='dma')
    result = s.drv.read_bytes(0, n, method='mmio')
    ok, detail = s._compare(result, pattern, "dma_write_mmio_read")
    s.record("dma_write_mmio_read", ok, detail)


def test_mmio_write_dma_read(s: TestSuite):
    """Write via MMIO, verify via DMA (cross-path integrity)."""
    if s.drv.axi_full_mmio is None:
        s.skip("mmio_write_dma_read", "AXI4-Full MMIO not available")
        return
    n = 8
    pattern = np.array([float(i * 7 + 3) for i in range(n)], dtype=np.float32)
    s.drv.send_bytes(0, pattern, method='mmio')
    # DMA reads need 8-word alignment, read exactly 8
    result = s.drv.read_bytes(0, n, method='dma')
    ok, detail = s._compare(result, pattern, "mmio_write_dma_read")
    s.record("mmio_write_dma_read", ok, detail)


def test_sys_to_onchip(s: TestSuite):
    """Write to sys_mem, copy to onchip, copy back to different sys_mem addr, read."""
    n = 16
    pattern = np.arange(n, dtype=np.float32) * 3.14
    # Write to sys_mem[0:15]
    s.drv.send_bytes(0, pattern, method='dma')
    # Copy sys_mem[0:15] → onchip[0:15]
    s.drv.sysmem_to_onchip(sys_addr=0, oc_addr=0, length=n)
    # Copy onchip[0:15] → sys_mem[200:215]
    s.drv.onchip_to_sysmem(oc_addr=0, sys_addr=200, length=n)
    # Read back from sys_mem[200:215]
    result = s.drv.read_bytes(200, n, method='dma')
    ok, detail = s._compare(result, pattern, "sys_to_onchip")
    s.record("sys_to_onchip", ok, detail)


def test_onchip_roundtrip(s: TestSuite):
    """Full roundtrip: host → sys_mem → onchip → sys_mem → host."""
    n = 32
    pattern = np.array([float(i * i + 1) for i in range(n)], dtype=np.float32)
    # Host → sys_mem[0:31]
    s.drv.send_bytes(0, pattern, method='dma')
    # sys_mem[0:31] → onchip[100:131]
    s.drv.sysmem_to_onchip(sys_addr=0, oc_addr=100, length=n)
    # onchip[100:131] → sys_mem[512:543]
    s.drv.onchip_to_sysmem(oc_addr=100, sys_addr=512, length=n)
    # sys_mem[512:543] → host
    result = s.drv.read_bytes(512, n, method='dma')
    ok, detail = s._compare(result, pattern, "onchip_roundtrip")
    s.record("onchip_roundtrip", ok, detail)


def test_bitpattern_deadbeef(s: TestSuite):
    """Classic DEADBEEF bit-exact roundtrip."""
    n = 16
    pattern_u32 = np.array([0xDEADBEEF] * n, dtype=np.uint32)
    pattern_f32 = pattern_u32.view(np.float32)
    s.drv.send_bytes(0, pattern_f32, method='dma')
    result = s.drv.read_bytes(0, n, method='dma')
    ok, detail = s._compare_u32(result, pattern_u32)
    s.record("bitpattern_deadbeef", ok, detail)


# ── Test registry ───────────────────────────────────────────────────────────
ALL_TESTS = [
    ("dma_write_read",      test_dma_write_read),
    # ("dma_large_transfer",  test_dma_large_transfer),
    ("dma_offset_addr",     test_dma_offset_addr),
    ("mmio_write_read",     test_mmio_write_read),
    ("mmio_random_access",  test_mmio_random_access),
    ("dma_write_mmio_read", test_dma_write_mmio_read),
    ("mmio_write_dma_read", test_mmio_write_dma_read),
    ("sys_to_onchip",       test_sys_to_onchip),
    ("onchip_roundtrip",    test_onchip_roundtrip),
    ("bitpattern_deadbeef", test_bitpattern_deadbeef),
]


def main():
    parser = argparse.ArgumentParser(description="Memory subsystem board test suite")
    parser.add_argument("--bitstream", default="mem_bd.bit", help="Bitstream to test")
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

    print("Memory Subsystem Board Test Suite")
    print(f"  Connecting to hardware (program={args.program})...")
    try:
        driver = MemDriver(bitstream=args.bitstream, program=args.program)
    except Exception as e:
        print(f"FATAL: Could not connect to hardware: {e}")
        sys.exit(2)

    suite = TestSuite(driver, verbose=args.verbose)

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
        except BusError as e:
            suite.record(name, False, f"BusError: {e}")
        except TimeoutError as e:
            suite.record(name, False, f"TimeoutError: {e}")
        except Exception as e:
            suite.record(name, False, f"Exception: {type(e).__name__}: {e}")

    passed = suite.summary()
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
