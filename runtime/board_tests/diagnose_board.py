#!/usr/bin/env python3
"""
board_tests/diagnose_board.py — Mini-TPU hardware diagnostics.

Probes the board and reports the state of all AXI-Lite registers, DMA status,
and FPGA overlay IPs. Useful for debugging connectivity and hang conditions.

Usage:
  python3 diagnose_board.py [--program] [--dump-devmem N] [--shift-probe N]

  --dump-devmem N   Read and print N words from DevMem starting at addr 0
  --shift-probe N   Write [0..N-1] and probe for the +2 board shift bug
"""

import argparse
import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from pynq_host import TpuDriver, REG_ADDR


def read_all_regs(mmio):
    """Dump all AXI-Lite registers."""
    print("\n--- AXI-Lite Register Dump ---")
    for name, offset in REG_ADDR.items():
        val = mmio.read(offset)
        print(f"  0x{offset:02X}  {name:15s} = 0x{val:08X} ({val})")


def probe_dma(tpu: TpuDriver):
    """Check DMA channel status."""
    print("\n--- DMA Channel Status ---")
    try:
        sc = tpu.dma.sendchannel
        rc = tpu.dma.recvchannel
        print(f"  sendchannel.running = {sc.running}")
        print(f"  recvchannel.running = {rc.running}")
    except Exception as e:
        print(f"  DMA probe failed: {e}")


def probe_overlay(tpu: TpuDriver):
    """List all IPs in the overlay."""
    print("\n--- Overlay IP List ---")
    for name in tpu.overlay.ip_dict:
        print(f"  {name}")


def probe_shift_bug(tpu: TpuDriver, n: int = 16):
    """Write [0..N-1] and probe for the board +2 word shift bug.

    Expected: result[i] == float(i)
    Bug symptom: result[i] == float(i+2)  (reads 2 words ahead)
    """
    print(f"\n--- Shift-Bug Probe (N={n}) ---")
    pattern = np.arange(n, dtype=np.float32)
    tpu.write_bram(0, pattern)
    result = tpu.read_bram(0, n)

    all_ok = True
    for i, (r, e) in enumerate(zip(result, pattern)):
        status = "OK" if abs(r - e) < 0.5 else f"MISMATCH (expected {e:.0f})"
        shift_hint = ""
        if abs(r - e) > 0.5:
            all_ok = False
            # Check if it matches i+2 (shift bug pattern)
            if 0 <= int(round(r)) < n and int(round(r)) == i + 2:
                shift_hint = " ← looks like +2 shift"
            elif 0 <= int(round(r)) < n and int(round(r)) == i + 1:
                shift_hint = " ← looks like +1 shift"
        print(f"  [{i:3d}]: got {r:8.2f}, expected {e:8.2f}  {status}{shift_hint}")

    if all_ok:
        print("  Result: no shift detected — board DMA appears correct")
    else:
        print("  Result: SHIFT BUG DETECTED — suspect BRAM output register config")
        print("  Fix: rebuild bitstream with BRAM output register disabled in TCL")


def dump_devmem(tpu: TpuDriver, n: int):
    """Read and print N words from DevMem[0:N]."""
    print(f"\n--- DevMem Dump (addr=0, n={n}) ---")
    result = tpu.read_bram(0, n)
    for i, v in enumerate(result):
        bits = int(np.float32(v).view(np.uint32))
        print(f"  [{i:4d}] {v:15.6g}  (0x{bits:08X})")


def main():
    parser = argparse.ArgumentParser(description="Mini-TPU board diagnostics")
    parser.add_argument("--program",    action="store_true",
                        help="Re-flash bitstream before probing")
    parser.add_argument("--dump-devmem", type=int, default=0, metavar="N",
                        help="Read N words from DevMem[0] and print")
    parser.add_argument("--shift-probe", type=int, default=16, metavar="N",
                        help="Run shift-bug probe with N words (default 16)")
    args = parser.parse_args()

    print("Mini-TPU Board Diagnostics")
    try:
        tpu = TpuDriver(program=args.program)
    except Exception as e:
        print(f"FATAL: Could not connect: {e}")
        sys.exit(2)

    read_all_regs(tpu.mmio)
    probe_dma(tpu)
    probe_overlay(tpu)

    if args.dump_devmem > 0:
        dump_devmem(tpu, args.dump_devmem)

    probe_shift_bug(tpu, n=args.shift_probe)


if __name__ == "__main__":
    main()
