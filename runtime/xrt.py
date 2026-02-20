"""
XRT HAL - Xilinx Alveo/Versal driver.

[PLANNED] This module will provide XRT/OpenCL-based execution 
for Alveo and Versal FPGA accelerator cards.
"""

from runtime.device import TPUDevice, DeviceBuffer, Execution


class XRTDevice(TPUDevice):
    """
    XRT-based driver for Alveo/Versal FPGAs.
    
    Uses XRT (Xilinx Runtime) with OpenCL compatibility layer
    for portability across Xilinx platforms.
    """
    
    def __init__(self, xclbin_path: str, device_index: int = 0):
        raise NotImplementedError("XRTDevice not yet implemented")
    
    @property
    def memory_size(self) -> int:
        raise NotImplementedError()
    
    def allocate(self, size: int, addr: int) -> DeviceBuffer:
        raise NotImplementedError()
    
    def transfer_h2d(self, data, buf: DeviceBuffer) -> None:
        raise NotImplementedError()
    
    def transfer_d2h(self, buf: DeviceBuffer, length: int):
        raise NotImplementedError()
    
    def submit(self, instructions: bytes) -> Execution:
        raise NotImplementedError()
    
    def sync(self, execution=None) -> None:
        raise NotImplementedError()
