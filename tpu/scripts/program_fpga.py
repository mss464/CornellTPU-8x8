#!/usr/bin/env python3
"""
Simple script to program the FPGA with a bitstream.
Used to separate FPGA programming from software tests.
"""

import argparse
import sys
from runtime.pynq_host import TpuDriver

def main():
    parser = argparse.ArgumentParser(description="Program FPGA with bitstream")
    parser.add_argument("bitstream", help="Path to bitstream (.bit)")
    parser.add_argument("--tpu-ip", default=None, help="TPU IP block name (auto-detect if not provided)")
    parser.add_argument("--dma-ip", default=None, help="DMA IP block name (auto-detect if not provided)")
    args = parser.parse_args()

    try:
        # TpuDriver(program=True) is the default, which calls overlay.download()
        TpuDriver(args.bitstream, tpu_name=args.tpu_ip, dma_name=args.dma_ip, program=True)
        print("Success: FPGA programmed.")
    except Exception as e:
        print(f"Error programming FPGA: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
