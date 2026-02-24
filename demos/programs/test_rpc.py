#!/usr/bin/env python3
"""
Minimal RPC Connection Test.
Writes DEADBEEF to the TPU's BRAM at address 0 and reads it back to verify
the RPC TCP link and basic `TpuDriver` functionality.
"""

import sys
from pathlib import Path
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.tuda import host, tudaInit, tudaMemcpy

@host
def run_rpc_test():
    print("Testing TUDA RPC Connection...")
    tudaInit()

    # The magic value we want to write
    magic_val = 0xDEADBEEF
    
    # Pack it into a 1-element float32 array (since TUDA expects float32 currently)
    # We use .view() to trick numpy into sending the exact bit pattern
    send_data = np.array([magic_val], dtype=np.uint32).view(np.float32)

    print("\n--- Writing to TPU BRAM [Addr 0] ---")
    tudaMemcpy(0, send_data, "HostToDevice")

    print("\n--- Reading from TPU BRAM [Addr 0] ---")
    recv_data = tudaMemcpy(0, 1, "DeviceToHost")
    
    # View the received float32 back as uint32 to check the hex pattern
    recv_val = recv_data.view(np.uint32)[0]

    print(f"Sent: 0x{magic_val:08X}")
    print(f"Recv: 0x{recv_val:08X}")

    if recv_val == magic_val:
        print("\nStatus: SUCCESS - RPC Link working perfectly! 🎉")
    else:
        print("\nStatus: FAILURE - Values do not match ❌")
        sys.exit(1)

if __name__ == "__main__":
    run_rpc_test()
