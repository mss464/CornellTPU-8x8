# Mini-TPU Runtime
# Execution orchestration and hardware abstraction

import os

try:
    from runtime.allocator import MemoryAllocator, allocator
    from runtime.device import TPUDevice, DeviceBuffer
except ImportError:
    from .allocator import MemoryAllocator, allocator
    from .device import TPUDevice, DeviceBuffer

def get_tpu_driver(*args, **kwargs):
    """
    Unified Factory for TpuDriver.
    Returns RemoteTpuDriver if MINITPU_HOST is set, else local pynq_host.TpuDriver.
    """
    host = os.environ.get("MINITPU_HOST")
    if host:
        try:
            from runtime.rpc_client import RemoteTpuDriver
        except ImportError:
            from .rpc_client import RemoteTpuDriver
        
        port = int(os.environ.get("MINITPU_PORT", 8080))
        return RemoteTpuDriver(host=host, port=port)
    else:
        try:
            from runtime.pynq_host import TpuDriver
        except ImportError:
            from .pynq_host import TpuDriver
        return TpuDriver(*args, **kwargs)

__all__ = [
    'MemoryAllocator', 'allocator',
    'TPUDevice', 'DeviceBuffer',
    'get_tpu_driver'
]
