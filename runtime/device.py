"""
TPU Device - Abstract hardware interface (HAL boundary).

[PLANNED] This module will define the abstract interface that all 
HAL implementations must follow.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import numpy as np


@dataclass
class DeviceBuffer:
    """Handle to an allocated buffer on the TPU device."""
    addr: int
    size: int
    _handle: any = None  # Backend-specific handle


class Execution:
    """Handle to a submitted execution (for async operations)."""
    pass


class TPUDevice(ABC):
    """
    Abstract TPU device interface.
    
    All HAL implementations (PYNQ, XRT, Simulator, ASIC GPIO) 
    must implement this interface.
    """
    
    @property
    @abstractmethod
    def memory_size(self) -> int:
        """Total device memory in bytes."""
        pass
    
    @abstractmethod
    def allocate(self, size: int, addr: int) -> DeviceBuffer:
        """Allocate a buffer at specified address."""
        pass
    
    @abstractmethod
    def transfer_h2d(self, data: np.ndarray, buf: DeviceBuffer) -> None:
        """Transfer data from host to device."""
        pass
    
    @abstractmethod
    def transfer_d2h(self, buf: DeviceBuffer, length: int) -> np.ndarray:
        """Transfer data from device to host."""
        pass
    
    @abstractmethod
    def submit(self, instructions: bytes) -> Execution:
        """Submit instructions for execution."""
        pass
    
    @abstractmethod
    def sync(self, execution: Optional[Execution] = None) -> None:
        """Wait for execution to complete."""
        pass
