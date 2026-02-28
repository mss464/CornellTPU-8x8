# Verification: Compute Mode (Mode 3)

End-to-end COMPUTE mode verification: VLOAD→VCOMPUTE→VSTORE kernel, DMA overlap, TMA instruction.

---

## Test Functions from `test_tpu_compute.py`

| Test function | Modes exercised | Verification |
|---|---|---|
| `test_compute_identity_kernel` | 1, 5, 7, 4, 3, 8, 6, 2 | Basic COMPUTE kernel: VLOAD zeros, identity MXU op, VSTORE identity result |
| `test_compute_vadd_kernel` | 1, 5, 7, 4, 3, 8, 6, 2 | COMPUTE kernel with vector ADD: VLOAD two inputs, VADD, VSTORE sum |
| `test_tma_instruction_in_kernel` | 1, 4, 3, 7, 8, 6, 2 | TMA instruction embedded in kernel: DM→L2, then compute using L2 as input |
| `test_dma_compute_overlap` | 1, 5, 7, 4, 3+1 concurrent, 8, 6, 2 | DMA (mode 1) and COMPUTE (mode 3) running concurrently; verify no data corruption |

## Mode Encoding

- **Mode 1** = WRITE_DEVMEM (host→device memory)
- **Mode 2** = READ_DEVMEM (device memory→host)
- **Mode 3** = COMPUTE (tensor core execution)
- **Mode 4** = WRITE_IRAM (host→compute tile instruction RAM)
- **Mode 5** = DM_TO_L2 (device memory→L2 SRAM)
- **Mode 6** = L2_TO_DM (L2 SRAM→device memory)
- **Mode 7** = L2_TO_L1 (L2→compute tile L1 BRAM)
- **Mode 8** = L1_TO_L2 (compute tile L1→L2 SRAM)

## FSM States / Behavioral Paths Covered

- Arbiter dispatch to `dma_engine` for modes 1, 2, 4, 5, 6
- Arbiter dispatch to `compute_ctrl` for mode 3
- Arbiter dispatch to `l2_ctrl` for modes 7, 8
- `instr_ready` de-assertion when any sub-FSM starts; re-assertion when all sub-FSMs idle
- `stream_ready` asserted by `dma_engine` when AXI-Stream write path is open
- Concurrent dispatch: mode 3 and mode 1 running simultaneously (`test_dma_compute_overlap`)
- Doorbell protocol: combined mode+doorbell write in a single AXI-Lite write (bit 4)

## Known Coverage Gaps

- Concurrent dispatch of `l2_ctrl` (modes 7/8) with `dma_engine` or `compute_ctrl` — only DMA+compute overlap is tested
- Arbiter behavior when a second doorbell arrives while same sub-FSM is already running (software contract violation)
- Mode 0 (IDLE explicit write) is not tested as a distinct command
- Invalid mode values (> 8) — RTL behavior undefined
