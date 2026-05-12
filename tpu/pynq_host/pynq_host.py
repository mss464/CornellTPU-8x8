import numpy as np
from pynq import Overlay, allocate

class MinitpuHost:
    def __init__(self, bitfile_path):
        self.overlay = Overlay(bitfile_path)
        
        # AXI Lite control 
        self.control_ip = self.overlay.tpu_slave_axi_lite_0
        self.AXI_LITE_BASE = self.control_ip.mmio.base_addr
        self.mmio = self.control_ip.mmio
        
        # AXI DMA
        self.dma = self.overlay.axi_dma_0
        self.send_channel = self.dma.sendchannel
        self.recv_channel = self.dma.recvchannel
        
        self.device_memory_size = 65536 * 4  # 256KB DevMem
        self.l2_memory_size = 32768 * 4      # 128KB L2
        self.l1_memory_size = 8192 * 4       # 32KB L1
        
    def write_reg(self, offset, val):
        self.mmio.write(offset, int(val))
        
    def read_reg(self, offset):
        return self.mmio.read(offset)
        
    def host_to_devmem(self, devmem_offset, data_array):
        """Mode 1: Write to Device Memory"""
        buf = allocate(shape=(len(data_array),), dtype=np.float32)
        np.copyto(buf, data_array)
        
        # Setup control regs
        # length
        self.write_reg(0x04, len(data_array)) 
        # devmem offset
        self.write_reg(0x18, devmem_offset) 
        # tpu mode = 1
        self.write_reg(0x00, 1)            
        
        self.send_channel.transfer(buf)
        self.send_channel.wait()
        buf.freebuffer()
        
    def devmem_to_host(self, devmem_offset, length):
        """Mode 2: Read from Device Memory"""
        buf = allocate(shape=(length,), dtype=np.float32)
        
        # length
        self.write_reg(0x04, length)
        # devmem offset
        self.write_reg(0x18, devmem_offset)
        # tpu mode = 2
        self.write_reg(0x00, 2)
        
        self.recv_channel.transfer(buf)
        self.recv_channel.wait()
        
        res = np.array(buf)
        buf.freebuffer()
        return res
        
    def devmem_to_l2(self, devmem_offset, l2_offset, length):
        """Mode 5: Bulk transfer from DevMem to L2"""
        # Set lengths
        self.write_reg(0x04, length)
        self.write_reg(0x18, devmem_offset)
        self.write_reg(0x1C, l2_offset)
        self.write_reg(0x00, 5) 
        
        self._wait_for_idle()

    def l2_to_devmem(self, l2_offset, devmem_offset, length):
         """Mode 6: Bulk transfer from L2 to DevMem"""
         self.write_reg(0x04, length)
         self.write_reg(0x18, devmem_offset)
         self.write_reg(0x1C, l2_offset)
         self.write_reg(0x00, 6)
         self._wait_for_idle()
         
    def l2_to_l1(self, l2_offset, l1_offset, length):
        """Mode 7: Bulk transfer from L2 to L1 Cache"""
        self.write_reg(0x04, length)
        self.write_reg(0x1C, l2_offset)
        self.write_reg(0x0C, l1_offset)
        self.write_reg(0x00, 7)
        self._wait_for_idle()
        
    def l1_to_l2(self, l1_offset, l2_offset, length):
        """Mode 8: Bulk transfer from L1 Cache to L2"""
        self.write_reg(0x04, length)
        self.write_reg(0x1C, l2_offset)
        self.write_reg(0x0C, l1_offset)
        self.write_reg(0x00, 8)
        self._wait_for_idle()

    def _wait_for_idle(self):
        # AXI Lite address 0x0C logic would need to reflect the idle state. 
        # Typically one polls until done bit is set. (Placeholder)
        pass 
