# Verification: device_mem.sv

**Role:** Device memory BRAM (65536 × 32-bit words, `blk_mem_gen_2`). Serves as the primary host-visible data buffer. Port A is used by `dma_engine` for host DMA reads and writes (modes 1 and 2). Port B is used by the `tma_engine` inside `l2_tile` for DevMem↔L2 block copies (modes 5 and 6).

**Test files:**
- `tpu/verification/system/test_device_mem.py` — dedicated device memory unit tests
- `tpu/verification/system/test_tpu.py` — indirect: every `write_bram` and `read_bram` touches device memory
- `tpu/verification/system/test_l2_tile.py` — indirect: DevMem↔L2 copies use Port B
- `tpu/verification/system/test_tpu_compute.py` — indirect: full compute flow staging through DevMem

**Test functions exercising this module:**

| Test function | Test file | Port / Path exercised |
|---|---|---|
| `test_devmem_write_read_integrity` | `test_device_mem.py` | Port A: write pattern (n=16), read back |
| `test_devmem_multiple_sizes` | `test_device_mem.py` | Port A: sizes 16, 64, 256 |
| `test_devmem_base_addr_offset` | `test_device_mem.py` | Port A: base address 0x100, 16 values |
| `test_dm_l2_roundtrip` | `test_l2_tile.py` | Port A write (mode 1), Port B read (mode 5), Port B write (mode 6) |
| `test_dm_l2_l1_l2_dm_roundtrip` | `test_l2_tile.py` | Port A + Port B (both directions) |
| `test_l2_l1_sizes` | `test_l2_tile.py` | Port A + Port B at sizes 16, 64, 128 |
| `test_l2_l1_base_addr_offset` | `test_l2_tile.py` | Port A at offsets 0x000, 0x100; Port B |
| `test_compute_identity_kernel` | `test_tpu_compute.py` | Port A at addrs 0, 8; Port B at 0, 8 |
| `test_dma_compute_overlap` | `test_tpu_compute.py` | Port A write concurrent with compute (addr 300) |

**Behavioral paths covered:**
- Port A write (`wea=1`): addresses 0, 8, 16, 32, 0x100, 0x200, 0x300
- Port A read (`ena=1, wea=0`): same address set, 1-cycle latency verified
- Port B (via tma_engine): DevMem→L2 reads, L2→DevMem writes
- 1-cycle registered read latency modeled correctly in both unit and system tests

**Known coverage gaps:**
- Port A and Port B simultaneous access to the same address — Port A/B conflict behavior (undefined for true-dual-port BRAM) not tested
- Large contiguous address ranges (addresses > 0x300 not extensively tested in unit tests; only `test_dma_compute_overlap` writes to addr 300+)
- Power-on default values (all zeros) not verified explicitly
