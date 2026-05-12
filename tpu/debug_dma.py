#!/usr/bin/env python3
"""
Minimal DMA read debug - hard 3s timeout, dump everything.
"""
import sys, os, time
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'runtime'))
from pynq_host import MemDriver
from pynq import allocate

def main():
    drv = MemDriver(bitstream="mem_bd.bit", program=True)
    log = []

    # -- Step 1: Write known pattern via DMA --
    n = 32
    pattern = np.arange(n, dtype=np.float32)
    drv.send_bytes(0, pattern, method='dma')
    drv.wait_idle()
    log.append("Write OK")

    # -- Step 2: Prep S2MM --
    length = n
    beat_length = (length + 7) // 8
    padded_len = beat_length * 8
    nbytes = padded_len * 4

    buf = allocate(shape=(padded_len,), dtype=np.float32, cacheable=False)
    buf[:] = 42.42

    # Check FSM state before read
    reg1_pre = drv.mmio.read(0x04)
    reg2_pre = drv.mmio.read(0x08)
    log.append(f"PRE-READ: reg1(idle)=0x{reg1_pre:08X} reg2(stream_ready)=0x{reg2_pre:08X}")

    # Reset and start S2MM
    drv.dma.write(0x30, 0x4)
    time.sleep(0.005)
    drv.dma.write(0x30, 0x10001)
    time.sleep(0.001)

    # Set destination
    drv.dma.write(0x48, buf.physical_address & 0xFFFFFFFF)
    drv.dma.write(0x4C, (buf.physical_address >> 32) & 0xFFFFFFFF)
    # Set length (arms S2MM)
    drv.dma.write(0x58, nbytes)
    time.sleep(0.001)

    sr_armed = drv.dma.read(0x34)
    log.append(f"S2MM armed: SR=0x{sr_armed:08X}")

    # Trigger FPGA read
    drv._write_reg("addr_sys", 0)
    drv._write_reg("length", length)
    drv._doorbell(2)

    # Poll with hard timeout
    t0 = time.time()
    deadline = t0 + 3.0
    final_sr = 0
    completed = False
    polls = 0
    while time.time() < deadline:
        sr = drv.dma.read(0x34)
        polls += 1
        if sr & 0x1002:
            completed = True
            final_sr = sr
            break
        if sr & 0x70:
            completed = True
            final_sr = sr
            log.append(f"DMA ERROR: SR=0x{sr:08X}")
            break
        time.sleep(0.01)

    if not completed:
        final_sr = drv.dma.read(0x34)

    elapsed = time.time() - t0
    log.append(f"Poll done: completed={completed} polls={polls} elapsed={elapsed:.3f}s")
    log.append(f"S2MM_SR_FINAL: 0x{final_sr:08X}")
    log.append(f"  Halted={bool(final_sr&1)} Idle={bool(final_sr&2)} DMAIntErr={bool(final_sr&0x10)}")
    log.append(f"  DMASlvErr={bool(final_sr&0x20)} DMADecErr={bool(final_sr&0x40)}")
    log.append(f"  IOC_Irq={bool(final_sr&0x1000)} Err_Irq={bool(final_sr&0x4000)}")

    bytes_xfr = drv.dma.read(0x58)
    log.append(f"S2MM_BYTES: {bytes_xfr}")

    # Check FSM after
    reg0 = drv.mmio.read(0x00)
    reg1 = drv.mmio.read(0x04)
    reg2 = drv.mmio.read(0x08)
    log.append(f"POST: reg0(mode)=0x{reg0:08X} reg1(idle)=0x{reg1:08X} reg2(stream)=0x{reg2:08X}")

    log.append(f"BUFFER[0:8]: {buf[0:8]}")
    log.append(f"EXPECTED[0:8]: {pattern[0:8]}")

    buf.freebuffer()

    with open('output_debug.txt', 'w') as f:
        f.write('\n'.join(log) + '\n')

main()
