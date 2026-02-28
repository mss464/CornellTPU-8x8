# Data Movement Modes

> **Scope:** Covers all 8 TPU data movement modes and the TMA instruction flow. See [memory_hierarchy.md](memory_hierarchy.md) for hierarchy overview.

---

## 4. Data Movement Modes

### Mode 1 — WRITE_DEVMEM (DDR → Device Memory)

```
Host DMA (PYNQ) ──AXI-Stream──► tpu_slave_axi_stream ──► device_mem Port A
```

**Timing:**
- `tpu.sv` detects `tpu_mode=1` in ST_IDLE, sets `data_write_en=1`, moves to ST_EXEC_WRITE
- Slave stream transitions IDLE→WRITE_FIFO on `S_AXIS_TVALID && write_en`
- BRAM write: `wea = data_write_en`, `addra = addr_devmem + write_pointer_stream`, `dina = S_AXIS_TDATA`
- `write_pointer_stream` increments on each successful AXI handshake (`fifo_wren = TVALID && TREADY`)
- **Note:** `wea=1` is asserted as soon as `data_write_en` goes high, before TREADY. The BRAM write fires on every clock where `wea=1`, using whatever `S_AXIS_TDATA` is at that moment. Words land correctly because `write_pointer_stream` only advances on actual handshakes.

**Completion:** `writes_done` asserts when `write_pointer_stream == dma_len - 1` or `S_AXIS_TLAST` fires. `tpu.sv` moves to ST_WAIT_DONE.

---

### Mode 2 — READ_DEVMEM (Device Memory → DDR)

```
device_mem Port A ──► tpu_master_axi_stream ──AXI-Stream──► Host DMA (PYNQ)
```

This is the most timing-sensitive path. See Section 5 for cycle-by-cycle detail.

---

### Mode 4 — WRITE_IRAM (DDR → IRAM)

Same slave stream path as Mode 1, but `instr_write_en=1` and words go to `blk_mem_gen_1`. The slave assembles 64-bit instructions from pairs of 32-bit words (`write_pointer_stream[0]` selects low/high half). `iram_addr` counter in `tpu.sv` tracks the 64-bit instruction address.

---

### Mode 3 — COMPUTE (Execute IRAM)

Tensorcore fetches instructions from IRAM Port B, decodes, and dispatches to MXU/VPU. L1 BRAM Port B provides data to MXU. No DMA path active.

---

### Mode 5 — DM_TO_L2 (Device Memory → L2 SRAM)

```
device_mem Port B ◄──► tma_engine ◄──► l2_sram Port B
```

Driven by `tma_engine` FSM in `DM2L2_READ` / `DM2L2_WRITE` states.

**Pipeline (1-cycle BRAM latency):**
```
DM2L2_READ cycle N:   drive dm_addr = dm_base + rd_count   (read from device mem)
                      if rd_valid_d1: write sram[l2_wr_addr_d1] = dm_dout  (write prev read to L2)
                      rd_valid_d1 ← 1, l2_wr_addr_d1 ← l2_base + rd_count
DM2L2_READ cycle N+1: dm_dout = data[dm_base + rd_count_N]  (data from previous read is valid)
                      sram write fires with correct data ✓
DM2L2_WRITE:          drain last word (rd_valid_d1 still latched)
```

---

### Mode 6 — L2_TO_DM (L2 SRAM → Device Memory)

Mirror of Mode 5, reads L2 Port B, writes to device memory Port B.

---

### Mode 7 — L2_TO_L1 (L2 SRAM → L1)

`tpu.sv` FSM directly drives L2 Port A and L1 Port A from `ST_EXEC_L22L1`:

```verilog
// Read L2 at addr_l2 + l2l1_rd_issued  (combinational address)
// l2l1_rd_valid=1 next cycle → write L1 at addr_ram + l2l1_wr_ptr
```

**Pipeline:** `l2l1_rd_issued` increments each cycle. `l2l1_rd_valid` is 1-cycle delayed (the registered flag that gates L1 write). L2 Port A douta = data at L2 addr from previous cycle (1-cycle BRAM latency). L1 write fires when `l2l1_rd_valid=1`, capturing the correct L2 data.

---

### Mode 8 — L1_TO_L2 (L1 → L2 SRAM)

Mirror of Mode 7. L1 Port A read → L2 Port A write, 1-cycle pipeline.

---

### TMA Instruction (MODE=2 in IRAM)

Tensorcore issues `tma_req` pulse to `tma_engine` via `l2_tile` and `tpu.sv`. Parameters (`tma_dm_base`, `tma_l2_base`, `tma_len`, `tma_dir`) are decoded from the 64-bit instruction. The engine runs the same DM↔L2 FSM as host-controlled Modes 5/6.

---

## 5. Mode 2 Read DMA — Cycle-by-Cycle Timing

This is the path exercised by the board smoke test (`devmem_roundtrip`).

### Datapath summary

```
read_pointer_stream (in tpu_master_axi_stream)
        │
        ▼
dma_addr = addr_devmem + read_pointer_stream   [combinational, in device_mem.sv]
        │
        ▼  [1-cycle BRAM latency]
blk_mem_gen_2.douta  (= devmem_rd_data in tpu.sv)
        │
        └── data_to_ddr ──► fifo_wr_data
                                │  [fifo_wr_en = !full && (valid_data || init_fill_valid)]
                                ▼
                          fifo4 (8 entries, REGISTERED read output)
                                │  [rd_en = axis_tvalid && TREADY && !empty]
                                ▼
                          fifo_rd_data = M_AXIS_TDATA
                                │
                          M_AXIS_TVALID = valid_d1   [1-cycle delay from axis_tvalid]
                                │
                                ▼
                           AXI-Stream → PYNQ DMA receive
```

### Pipeline stages in read path

| Stage | Delay | Source |
|-------|-------|--------|
| BRAM address → BRAM douta | 1 cycle | blk_mem_gen_2 |
| fifo_wr_en → rd_data in FIFO | 0 cycles (same cycle write, 1 cycle to appear on rd_data) | fifo4.sv |
| axis_tvalid → M_AXIS_TVALID | 1 cycle | valid_d1 register |
| fifo_rd_en → M_AXIS_TDATA update | 1 cycle | fifo4 registered read output |

Total pipeline depth from BRAM address presented to host DMA receiving the word: **2–3 cycles** (BRAM: 1 + FIFO: 1 + valid delay: 1, pipelined so throughput = 1 word/cycle at steady state).

### Cycle trace for READ_DEVMEM with N=16 words

`C_M_START_COUNT=32` means INIT_COUNTER runs for 32 cycles.
`init_fill_valid` fires for `count <= 8 && count <= N`.

**Legend:**
- `r_ptr`: `read_pointer_stream` (registered — value shown is what's active at this cycle's START)
- `BRAM_addr`: `addr_devmem + r_ptr` (combinational)
- `BRAM_douta`: data output (1-cycle delay: reflects addr from previous cycle)
- `fill_v`: `init_fill_valid` (registered — value at cycle START; set as NBA at cycle end)
- `FIFO_wr`: what gets written to FIFO this cycle

```
Cycle | State   |cnt| r_ptr→new| BRAM_addr | fill_v→new | BRAM_douta | FIFO_wr
------|---------|---|----------|-----------|------------|------------|----------
 0    | IDL→IC  | 0 |  0 →  0  | base+0    |  0  → 0   | stale      | —        (Block2 sees old state=IDLE)
 1    | IC      | 0 |  0 →  0  | base+0    |  0  → 0   | data[0]*   | —        (reset=1 → Block2 resets r_ptr=0)
 2    | IC      | 1 |  0 →  1  | base+0    |  0  → 1   | data[0]    | —        (fill_v was 0)
 3    | IC      | 2 |  1 →  2  | base+1    |  1  → 1   | data[0]    | FIFO[0]=data[0] ✓
 4    | IC      | 3 |  2 →  3  | base+2    |  1  → 1   | data[1]    | FIFO[1]=data[1] ✓
 5    | IC      | 4 |  3 →  4  | base+3    |  1  → 1   | data[2]    | FIFO[2]=data[2] ✓
 6    | IC      | 5 |  4 →  5  | base+4    |  1  → 1   | data[3]    | FIFO[3]=data[3] ✓
 7    | IC      | 6 |  5 →  6  | base+5    |  1  → 1   | data[4]    | FIFO[4]=data[4] ✓
 8    | IC      | 7 |  6 →  7  | base+6    |  1  → 1   | data[5]    | FIFO[5]=data[5] ✓
 9    | IC      | 8 |  7 →  8  | base+7    |  1  → 1   | data[6]    | FIFO[6]=data[6] ✓
10    | IC      | 9 |  8 →  9  | base+8    |  1  → 0   | data[7]    | FIFO[7]=data[7] ✓ (FIFO full)
11..31| IC      |…  |  9 →  9  | base+9    |  0  → 0   | data[8]    | — (fill_v=0 or FIFO full)
32    | IC→SS   |31 |  9        | base+9    |  0         | data[8]    | —
33    | SS      |—  |  9        | base+9    | —          | data[8]    | axis_tvalid=1, fifo_rd_en fires
```

*At cycle 1, `reset=1` fires Block2's reset branch. But `r_ptr` was already 0. The "reset" just holds it at 0.
`data[0]` shown for BRAM_douta at cycle 1 because `base+0` was presented at cycle 0.

### What happens if BRAM latency is 2 cycles

With 2-cycle BRAM: `BRAM_douta` reflects addr from **two cycles ago**:

```
Cycle | r_ptr | BRAM_addr | BRAM_douta (2-cycle) | FIFO_wr
  3   |   1   | base+1    | data[addr@cycle1=base+0]=data[0]  | FIFO[0]=data[0]
  4   |   2   | base+2    | data[addr@cycle2=base+0]=data[0]  | FIFO[1]=data[0]  ← DUPLICATE
  5   |   3   | base+3    | data[addr@cycle3=base+1]=data[1]  | FIFO[2]=data[1]
  6   |   4   | base+4    | data[addr@cycle4=base+2]=data[2]  | FIFO[3]=data[2]
```

**2-cycle BRAM expected output: `[0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]`**
(first word repeated, last word truncated)
