#!/usr/bin/env python3
import sys
import os
import numpy as np
import time

# Add runtime to path
# On the board, reproduce_bus_error.py is in DEPLOY_DIR/board_tests/
# runtime is in DEPLOY_DIR/runtime/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from runtime.pynq_host import TpuDriver

def main():
    print("Reproduction Script: Isolating Bus Error for N=9")
    try:
        # bitstream should be in DEPLOY_DIR/minitpu.bit
        tpu = TpuDriver(bitstream="minitpu.bit", program=False)
    except Exception as e:
        print(f"FATAL: Could not connect to TPU: {e}")
        return

    n = 9
    print(f"Testing write_bram with N={n}...")
    pattern = np.arange(n, dtype=np.float32)
    try:
        tpu.write_bram(0, pattern)
        print("  write_bram OK")
    except Exception as e:
        print(f"  write_bram FAILED: {e}")
        return

    print(f"Testing read_bram with N={n}...")
    try:
        result = tpu.read_bram(0, n)
        print("  read_bram OK")
        print(f"  Result: {result}")
        if np.allclose(result, pattern):
            print("  MATCH")
        else:
            print(f"  MISMATCH! Expected {pattern}")
    except Exception as e:
        print(f"  read_bram FAILED: {e}")
        return

if __name__ == "__main__":
    main()
