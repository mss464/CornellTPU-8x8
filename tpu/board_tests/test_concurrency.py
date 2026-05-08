#!/usr/bin/env python3
import sys
import os
import numpy as np
import time

# Add runtime to path (handles both local and board deployment)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'runtime'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))
from pynq_host import MemDriver

def make_instr(mode, addr_a, addr_b, addr_out, length, opcode):
    # mode[1:0], addr_a[12:0], addr_b[12:0], addr_out[12:0], len[22:0], opcode[9:0]
    # Note: len and opcode overlap in the decoder, but mode selection handles it.
    instr = (int(mode) & 0x3) << 62
    instr |= (int(addr_a) & 0x1FFF) << 49
    instr |= (int(addr_b) & 0x1FFF) << 36
    instr |= (int(addr_out) & 0x1FFF) << 23
    instr |= (int(length) & 0x1FFF) << 10 # Place length above opcode if needed
    instr |= (int(opcode) & 0x3FF)
    return instr

def main():
    print("Concurrent TPU Execution Test")
    
    # Initialize driver
    try:
        drv = MemDriver(bitstream="mem_bd.bit")
    except Exception as e:
        print(f"Failed to initialize driver: {e}")
        sys.exit(1)

    # 1. Prepare instructions for a long-running VADD task
    # We'll do a VADD of length 2000 (takes some time)
    # VADD mode is 2 (from compute_tile.sv dispatch)
    # We'll add data at L1 address 0 and L1 address 1000, results to L1 address 2000.
    vadd_instr = make_instr(mode=2, addr_a=0, addr_b=1000, addr_out=2000, length=2000, opcode=0)
    halt_instr = make_instr(mode=3, addr_a=0, addr_b=0, addr_out=0, length=0, opcode=0x3FF)
    
    # Split 64-bit into 32-bit words for load_instructions
    instructions = []
    for i in [vadd_instr, halt_instr]:
        instructions.append(i & 0xFFFFFFFF)
        instructions.append((i >> 32) & 0xFFFFFFFF)
    
    print("Loading instructions...")
    drv.load_instructions(instructions)

    # 2. Prepare data in L1 for the VADD
    print("Preparing L1 data...")
    # Fill L1 [0..2000] with some values
    data_a = np.arange(1000, dtype=np.float32)
    data_b = np.arange(1000, 2000, dtype=np.float32)
    
    # L1 is accessed via Port A (Scalar DMA) or copy modes.
    # We'll use sysmem_to_onchip.
    # First write to sysmem, then copy to onchip.
    sys_addr = 0
    drv.send_bytes(sys_addr, np.concatenate([data_a, data_b]))
    drv.sysmem_to_onchip(sys_addr, 0, 2000)

    # 3. Start Compute ASYNC
    print("Starting TPU compute (async)...")
    start_time = time.time()
    drv.run_compute(async_run=True)

    # 4. While Compute is running, perform a DMA transfer to a DIFFERENT region in sysmem
    # This demonstrates that the DMA channel is not blocked by the Compute channel.
    print("Starting concurrent DMA transfer...")
    dma_data = np.random.rand(1024).astype(np.float32)
    dma_addr = 4096 # Offset to avoid conflict
    drv.send_bytes_async(dma_addr, dma_data)
    
    # 5. Wait for both
    print("Waiting for DMA to finish...")
    drv.wait_dma_idle()
    dma_time = time.time() - start_time
    print(f"DMA finished in {dma_time:.4f}s")
    
    print("Waiting for Compute to finish...")
    drv.wait_compute_idle()
    compute_time = time.time() - start_time
    print(f"Compute finished in {compute_time:.4f}s")

    # 6. Verify results
    print("Verifying results...")
    # Read back DMA data
    read_back_dma = drv.read_bytes(dma_addr, 1024)
    if np.allclose(read_back_dma, dma_data):
        print("  PASS: Concurrent DMA data integrity")
    else:
        print("  FAIL: Concurrent DMA data corruption")

    # Read back Compute results (copy back from L1 first)
    drv.onchip_to_sysmem(2000, sys_addr + 3000, 1000)
    compute_results = drv.read_bytes(sys_addr + 3000, 1000)
    expected = data_a + data_b
    if np.allclose(compute_results, expected):
        print("  PASS: Compute result integrity")
    else:
        print("  FAIL: Compute result error")

if __name__ == "__main__":
    main()
