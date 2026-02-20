import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from runtime.tuda import host, tudaMalloc
from runtime.allocator import allocator

def test_tuda_api():
    @host
    def mock_host_logic():
        # Test the allocator through the tuda layer (dummy device context setup)
        from runtime.tuda import _device, TUDADevice
        import runtime.tuda as t
        
        # We can't init real TpuDriver on unit tests off-board, 
        # so we mock the device core.
        class MockDriver:
            pass
            
        t._device = type("MockTUDADevice", (), {"tudaMalloc": lambda self, n, s: allocator.alloc(n, s)})()
        
        addr = t.tudaMalloc("test_buf", 16)
        assert addr == 0, "TUDA allocator mapping failed"
        addr2 = t.tudaMalloc("test_buf2", 8)
        assert addr2 == 16, "TUDA bump alloc failed"

    mock_host_logic()
    print("[SUCCESS] TUDA software API verified!")

if __name__ == "__main__":
    test_tuda_api()
