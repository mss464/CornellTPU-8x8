"""
ASIC GPIO HAL - Driver for taped-out ASIC via GPIO interface.

[PLANNED] This module will provide GPIO-based control for 
post-silicon testing of the Mini-TPU ASIC.

Pin assignment (8-in / 8-out / 8-bidir):
- IN: clk, nreset, cmd_valid, cmd[2:0], reserved[1:0]
- OUT: done, ready, data_valid, reserved[4:0]
- BIDIR: data[7:0]
"""

from runtime.device import TPUDevice, DeviceBuffer, Execution


class ASICGPIODevice(TPUDevice):
    """
    GPIO-based driver for taped-out ASIC.
    
    Uses a simple command protocol over GPIO pins for
    post-silicon testing and bring-up.
    """
    
    def __init__(self, gpio_interface):
        """
        Args:
            gpio_interface: Backend for GPIO control (e.g., FTDI, RPi GPIO)
        """
        raise NotImplementedError("ASICGPIODevice not yet implemented")
    
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
