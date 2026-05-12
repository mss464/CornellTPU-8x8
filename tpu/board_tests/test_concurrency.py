#!/usr/bin/env python3
import argparse
import sys
import os
import numpy as np
import time

# Prefer the runtime deployed beside this test over stale copies in $HOME/runtime.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
for _path in (
    os.path.join(_THIS_DIR, '..', '..', 'runtime'),
    os.path.join(_THIS_DIR, 'runtime'),
    os.path.join(_THIS_DIR, '..', 'runtime'),
):
    _path = os.path.abspath(_path)
    if _path not in sys.path:
        sys.path.insert(0, _path)
from pynq_host import MemDriver
import pynq_host as _pynq_host
print(f"Using pynq_host from: {_pynq_host.__file__}")

def make_instr(mode, addr_a, addr_b, addr_out, length, opcode):
    # mode[1:0], addr_a[12:0], addr_b[12:0], addr_out[12:0], len[22:0], opcode[9:0]
    # Note: len and opcode overlap in the decoder. Compute instructions use opcode=0
    # so the full length field can be encoded directly.
    instr = (int(mode) & 0x3) << 62
    instr |= (int(addr_a) & 0x1FFF) << 49
    instr |= (int(addr_b) & 0x1FFF) << 36
    instr |= (int(addr_out) & 0x1FFF) << 23
    instr |= (int(length) & 0x7FFFFF)
    if opcode:
        instr = (instr & ~0x3FF) | (int(opcode) & 0x3FF)
    return instr

def main():
    parser = argparse.ArgumentParser(description="Concurrent TPU execution board test")
    parser.add_argument("--bitstream", default="mem_bd.bit", help="Bitstream to test")
    parser.add_argument("--program", action="store_true",
                        help="Re-flash FPGA bitstream before running test")
    parser.add_argument("--latency", type=int, default=0,
                        help="BRAM read latency selection (0=1 cycle, 1=2 cycles). Default=0.")
    args = parser.parse_args()

    print("Concurrent TPU Execution Test")
    
    # Initialize driver
    try:
        drv = MemDriver(bitstream=args.bitstream, program=args.program, latency_mode=args.latency)
    except Exception as e:
        print(f"Failed to initialize driver: {e}")
        sys.exit(1)

    # 1. Prepare instructions for a long-running VADD task
    # VADD mode is 2 (from compute_tile.sv dispatch)
    # vadd.sv is a raw 32-bit wrapping adder, so verification is bit-exact.
    vadd_len = 1024
    vadd_repeats = 128
    addr_a = 0
    addr_b = addr_a + vadd_len
    addr_out = addr_b + vadd_len
    vadd_instr = make_instr(mode=2, addr_a=addr_a, addr_b=addr_b, addr_out=addr_out, length=vadd_len, opcode=0)
    halt_instr = make_instr(mode=3, addr_a=0, addr_b=0, addr_out=0, length=0, opcode=0x3FF)
    
    # Split 64-bit into 32-bit words for load_instructions
    instructions = []
    for i in ([vadd_instr] * vadd_repeats) + [halt_instr]:
        instructions.append(i & 0xFFFFFFFF)
        instructions.append((i >> 32) & 0xFFFFFFFF)
    
    print("Loading instructions...")
    drv.load_instructions(instructions)

    # 2. Prepare data in L1 for the VADD
    print("Preparing L1 data...")
    data_a = np.arange(vadd_len, dtype=np.float32)
    data_b = np.arange(vadd_len, 2 * vadd_len, dtype=np.float32)
    
    # L1 is accessed via Port A (Scalar DMA) or copy modes.
    # We'll use sysmem_to_onchip.
    # First write to sysmem, then copy to onchip.
    sys_addr = 0
    drv.send_bytes(sys_addr, np.concatenate([data_a, data_b]))
    drv.sysmem_to_onchip(sys_addr, addr_a, 2 * vadd_len)

    # 3. Start Compute ASYNC
    print("Starting TPU compute (async)...")
    start_time = time.time()
    drv.run_compute(async_run=True)

    # 4. While Compute is running, perform a DMA transfer to a DIFFERENT region in sysmem
    # This demonstrates that the DMA channel is not blocked by the Compute channel.
    print("Starting concurrent DMA transfer...")
    rng = np.random.RandomState(12345)
    dma_data = rng.rand(1024).astype(np.float32)
    dma_addr = 8192 # Offset to avoid conflict
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
    failures = 0

    # Read back DMA data
    read_back_dma = drv.read_bytes(dma_addr, 1024)
    if np.allclose(read_back_dma, dma_data):
        print("  PASS: Concurrent DMA data integrity")
    else:
        failures += 1
        print("  FAIL: Concurrent DMA data corruption")

    # Read back Compute results (copy back from L1 first)
    result_sys_addr = 12288
    drv.onchip_to_sysmem(addr_out, result_sys_addr, vadd_len)
    compute_results = drv.read_bytes(result_sys_addr, vadd_len)
    expected_bits = data_a.view(np.uint32) + data_b.view(np.uint32)
    result_bits = compute_results.view(np.uint32)
    if np.array_equal(result_bits, expected_bits):
        print("  PASS: Compute result integrity")
    else:
        failures += 1
        print("  FAIL: Compute result error")
        bad = np.flatnonzero(result_bits != expected_bits)[:8]
        for idx in bad:
            print(
                f"    [{idx}]: got 0x{int(result_bits[idx]):08X}, "
                f"expected 0x{int(expected_bits[idx]):08X}"
            )

    if failures:
        sys.exit(1)

if __name__ == "__main__":
    main()
