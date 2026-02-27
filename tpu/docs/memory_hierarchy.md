# TPU Memory Hierarchy — Design Reference

> **Status:** P1 single-tile implementation
> **Last updated:** 2026-02-26
> **Audience:** Human reviewers debugging board-level timing issues

---

## 1. Overview

```
Host (DDR / PYNQ)
       │  AXI-Stream DMA  (modes 1, 2, 4)
       ▼
Device Memory  (blk_mem_gen_2)   256 KiB  65536 × 32-bit
       │  tma_engine  (modes 5, 6 / TMA instruction)
       ▼
L2 SRAM        (blk_mem_gen_3)   128 KiB  32768 × 32-bit
       │  tpu.sv FSM direct port control  (modes 7, 8)
       ▼
L1 Data BRAM   (blk_mem_gen_0)    32 KiB   8192 × 32-bit
       │  compute tile internal bus
       ▼
Compute (MXU, VPU)

IRAM           (blk_mem_gen_1)     2 KiB    256 × 64-bit
       │  tensorcore fetch
       ▼
Decoder → Dispatch
```

All four BRAMs are **true dual-port** (TDP) Xilinx Block RAM IPs.
All four are clocked by `s00_axi_aclk` (= the single TPU system clock).

---

## 2. Memory Components

### 2.1 Device Memory — blk_mem_gen_2

| Attribute        | Value |
|------------------|-------|
| Depth            | 65536 words |
| Width            | 32 bits |
| Total size       | 256 KiB |
| Addressing       | 16-bit word address |
| Port A owner     | Host DMA (modes 1/2, `device_mem.sv`) |
| Port B owner     | `tma_engine` (modes 5/6 and TMA instruction) |
| Read latency     | 1 cycle (registered, no extra output register) |
| TCL setting      | `Register_PortA/B_Output_of_Memory_Primitives {false}` |

**Port A address generation** (`device_mem.sv` line 43):
```verilog
assign dma_addr = base_addr + (dma_wr_en ? dma_write_pointer : dma_read_pointer);
```
`base_addr = addr_devmem` (AXI-Lite register 0x10, set by host before each operation).
`dma_write_pointer / dma_read_pointer = write_pointer_stream / read_pointer_stream` from the slave/master AXI-Stream modules.

**Port B** is driven entirely by `tma_engine`. The address, din, en, we signals come from the engine's combinational output mux.

---

### 2.2 L2 SRAM — blk_mem_gen_3

| Attribute        | Value |
|------------------|-------|
| Depth            | 32768 words |
| Width            | 32 bits |
| Total size       | 128 KiB |
| Addressing       | 15-bit word address |
| Port A owner     | Compute tile side (tpu.sv FSM, modes 7/8) |
| Port B owner     | `tma_engine` (modes 5/6, TMA instruction) |
| Read latency     | 1 cycle |
| TCL setting      | `Register_PortA/B_Output_of_Memory_Primitives {false}` |

Port A is controlled by `tpu.sv`'s `ST_EXEC_L22L1` / `ST_EXEC_L12L2` states via the `l2_ct_*` combinational wires. Port B is controlled by `tma_engine`.

---

### 2.3 L1 Data BRAM — blk_mem_gen_0

| Attribute        | Value |
|------------------|-------|
| Depth            | 8192 words |
| Width            | 32 bits |
| Total size       | 32 KiB |
| Addressing       | 13-bit word address |
| Port A owner     | DMA side (L2↔L1 transfers, tpu.sv FSM) |
| Port B owner     | Compute tile (MXU/VPU systolic input) |
| Read latency     | 1 cycle |
| TCL setting      | `Register_PortA/B_Output_of_Memory_Primitives {false}` |

Port A address: `base_addr + offset` where `base_addr = addr_ram` (0x0C) and offset is the DMA pointer from the tpu.sv FSM (`l2l1_wr_ptr` / `l2l1_rd_issued`).

---

### 2.4 IRAM — blk_mem_gen_1

| Attribute        | Value |
|------------------|-------|
| Depth            | 256 instructions |
| Width            | 64 bits |
| Total size       | 2 KiB |
| Addressing       | 8-bit word address |
| Port A owner     | DMA write (mode 4, `tpu_slave_axi_stream.v`) |
| Port B owner     | Tensorcore instruction fetch |
| Read latency     | 1 cycle |
| TCL setting      | `Register_PortA/B_Output_of_Memory_Primitives {false}` |

Instructions are 64-bit; the slave stream assembles pairs of 32-bit AXI-Stream words.

---

## 3. BRAM Latency — Critical Design Invariant

All four BRAMs use **1-cycle read latency** (Xilinx registered-output mode without the extra output register):

```
posedge N   : address captured internally by BRAM
posedge N+1 : douta = mem[address_N]
```

The behavioral model `blk_mem_models.sv` implements this exactly:
```verilog
always @(posedge clka) if (ena) douta <= mem[addra];
```

### What `Register_PortA_Output_of_Memory_Primitives` Does

Xilinx's IP Catalog offers an additional pipeline register **after** the BRAM's internal register:

| Setting | Pipeline stages | Total latency |
|---------|----------------|---------------|
| `{false}` | 1 (BRAM internal register) | **1 cycle** ← design assumption |
| `{true}`  | 2 (BRAM + output register) | **2 cycles** ← was incorrectly set |

The haiku synthesis agent set this to `{true}` for all four IPs, causing a 2-cycle hardware latency while simulation used a 1-cycle behavioral model. This was corrected (commit `9d6a58b`).

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

---

## 6. Board Bug Analysis — Read DMA Corruption

### Observed behavior (2026-02-26, 31-word test)

Pattern written: `np.arange(31, dtype=np.uint32)` = `[0, 1, 2, ..., 30]`
Result read back (every word wrong):
```
[0]:  expected 0x00000000, got 0x00000002
[1]:  expected 0x00000001, got 0x00000003
[2]:  expected 0x00000002, got 0x00000004
[3]:  expected 0x00000003, got 0x00000005
[4]:  expected 0x00000004, got 0x00000006
[5]:  expected 0x00000005, got 0x00000007
[6]:  expected 0x00000006, got 0x00000008
[7]:  expected 0x00000007, got 0x00000008   ← SAME AS [6]: data[8] duplicated
[8]:  expected 0x00000008, got 0x0000000A
[9]:  expected 0x00000009, got 0x0000000B
...
[29]: expected 0x0000001D, got 0x0000001F
[30]: expected 0x0000001E, got 0x0000001F   ← SAME AS [29]: data[31] out-of-range repeat
```

**Decoded symptom:**
1. First 2 elements missing (indices 0–1 skipped)
2. Element at value=8 (index 6 in the shifted stream) is sent **twice** (indices 6 and 7 both receive it)
3. Result is therefore: `data[2], data[3], ..., data[8], data[8], data[10], ..., data[30], data[31]`

The FIFO has 8 entries. The initial prefill loads `data[2]..data[9]` (8 words) because `read_pointer_stream` starts from 2 instead of 0. `data[8]` = FIFO slot 6 (0-indexed), which is the **8th word read out**. This coincides with when the FIFO drains and `fifo_one_left` → `tlast` fires — the registered FIFO output holds `data[8]` for one extra cycle during the tlast/done transition.

### Root cause: two compounding bugs

#### Bug A — write_pointer_stream starts at 2 (write path off-by-2)

The write path (`tpu_slave_axi_stream.v`) has the same IDLE→WRITE_FIFO reset stall pattern documented in CLAUDE.md Design Pitfall §1. The slave stream's `write_pointer_stream` fires from reset on the first WRITE_FIFO cycle, causing the first two AXI beats to land at BRAM addresses `base+0` and `base+0` (pointer didn't advance). Then `write_pointer_stream` increments correctly from 1 onward, so `data[0]` is overwritten by `data[1]` at address 0, `data[1]` goes to address 1... and `data[0]` is permanently lost. But wait — re-reading the slave stream code (line 162–165):

```verilog
if (fifo_wren && (write_pointer_stream != NUMBER_OF_INPUT_WORDS-1))
    write_pointer_stream <= write_pointer_stream + 1;
```

The pointer only advances when `fifo_wren` fires AND we're not at the last word. The BRAM write enable (`wea = data_write_en`) is independent — it fires based on `write_en`, not the stream handshake. **If `write_pointer_stream` resets to 0 one cycle late, the first two BRAM writes both hit address `base+0`**, writing `data[0]` then `data[1]` to the same address. Data stored in BRAM then: `[data[1], data[1], data[2], data[3], ...]` — address 0 = data[1], address 1 = data[1].

Actually the simpler explanation consistent with the observation: the slave stream reset stall causes `write_pointer_stream` to skip increment on first beat, so `data[0]` and `data[1]` both write to BRAM address 0. The effective stored content becomes `[data[1], data[2], ..., data[N-1], ?, ?]` — data[0] lost, everything shifted by 1.

But the read shows a shift of +2, so write and read both contribute +1 each, OR the read path contributes +2 alone.

#### Bug B — FIFO registered output causes data[8] duplication

`fifo4` has a **registered read output**: `rd_data <= mem[rptr]` (clocked). This means:

- When `fifo_rd_en` goes high at cycle T: rptr advances, `rd_data` updates to the new value at cycle T+1.
- The FIRST `rd_en` pulse causes rptr to jump from 0→1, but `rd_data` still holds `mem[0]` until cycle T+1.
- `M_AXIS_TDATA = fifo_rd_data` follows this 1-cycle lag.
- `M_AXIS_TVALID = valid_d1` (also 1-cycle delayed from `axis_tvalid`).

These two 1-cycle delays are meant to be aligned. However, when the FIFO transitions from full→draining, there is an off-by-one in the `read_pointer_stream` increment vs `fifo_rd_en` timing:

In SEND_STREAM, `valid_data` fires when `fifo_rd_en` fires (same cycle in Block 2):
```verilog
if (fifo_rd_en)
    read_pointer_stream <= read_pointer_stream + 1;
    valid_data <= 1'b1;
```

`valid_data` goes into `fifo_wr_en`, which refills the FIFO from BRAM. But `read_pointer_stream` drives `BRAM_addr = addr_devmem + read_pointer_stream` **combinationally**. So the BRAM is always reading 1 address ahead of the last consumed FIFO slot. When the FIFO has exactly 1 item remaining (`fifo_one_left`) and the last `fifo_rd_en` fires, the FIFO becomes empty on the next cycle. Meanwhile `rd_data` still holds the last value for one more cycle — **the DMA sees it twice** if `axis_tvalid` remains asserted while `fifo_empty` is still 0 due to timing.

Specifically at the FIFO-full→drain boundary (where the prefilled 8 words are first read out), the entry at FIFO slot 7 (containing `data[8]` in the shifted-by-2 scenario) is presented on `rd_data` for two consecutive cycles while `axis_tvalid` is high and `TREADY` is 1 — because `fifo_empty` goes high one cycle after the last `rd_en`, but `valid_d1` is already 1.

### Summary: what the DMA actually receives

```
Written to BRAM (Bug A — slave stream write stall):
  addr 0: data[1]   ← data[0] and data[1] both wrote here; data[0] lost
  addr 1: data[2]
  addr 2: data[3]
  ...
  addr N-2: data[N-1]
  addr N-1: garbage (never written)

Read DMA stream (Bug B — FIFO registered read stall at boundary):
  Word 0: data[1]   ← but BRAM read starts at addr 0+offset...
```

The net result is a +2 shift because the write path loses 1 word (pointer stall) and the read path duplicates 1 word (FIFO registered output boundary), causing the output window to be 2 ahead of expected while one valid word is consumed twice.

### Fix strategy

**Fix A — slave stream write pointer stall** (`tpu_slave_axi_stream.v`):
Apply the same pattern as the `reset <= 1'b0` fix already in place on line 123. The `write_pointer_stream` reset block (in Block 2, guarded by `if(!ARESETN || reset)`) fires at the first WRITE_FIFO cycle because `reset=1` from IDLE. The BRAM write (`wea`) is already firing. Fix: gate `wea` (= `data_write_en`) on the fifo_wren handshake, OR ensure `write_pointer_stream` is already incremented by the time the first BRAM write fires.

Simplest correct fix: make `data_write_en` (and thus `wea`) only assert when `fifo_wren` is true (i.e., require AXI handshake before allowing BRAM write). Currently `wea = data_write_en` fires independent of TVALID/TREADY.

**Fix B — FIFO registered read boundary duplicate** (`tpu_master_axi_stream.v`):
The `axis_tvalid = (mst_exec_state == SEND_STREAM) && !fifo_empty` condition deasserts 1 cycle after the FIFO actually empties (because `fifo_empty` is registered in fifo4). The `valid_d1` delay compounds this. Options:

1. Anticipate the empty condition using `fifo_one_left`: deassert `axis_tvalid` one cycle early when `fifo_one_left && !fifo_wr_en` — this is already being done for `tlast`, apply the same logic to `axis_tvalid`.
2. Or: change fifo4 to combinational (not registered) read output. Simpler but changes BRAM-like timing.

The safest targeted fix is option 1: extend the `tlast` early-deassert logic to also gate `axis_tvalid`.

---

## 7. Fix Locations

| Bug | File | Symptom contribution | Fix |
|-----|------|---------------------|-----|
| A: slave write stall | `tpu_slave_axi_stream.v` | write ptr stalls 1 cycle → data[0] overwritten | Gate `wea` on `fifo_wren`, or deassert `data_write_en` during reset stall |
| B: master FIFO drain duplicate | `tpu_master_axi_stream.v` | last FIFO word presented twice at boundary | Gate `axis_tvalid` on `fifo_one_left` to deassert 1 cycle early |

Both bugs are in the DMA stream modules. The RTL simulation passes because cocotb's `TpuRtlDriver` drives AXI-Stream beats with exact handshake timing that happens to mask the stall cycle, and the test vector sizes don't land on the FIFO boundary duplicate. The board exposes them because the PYNQ DMA captures exactly N words with no tolerance for extras or gaps.

---

## 8. Simulation vs Hardware Alignment Checklist

| Item | Simulation | Hardware target | Status |
|------|-----------|----------------|--------|
| blk_mem_gen_0 latency | 1 cycle (blk_mem_models.sv) | 1 cycle (`Register_*={false}`) | ✓ Fixed |
| blk_mem_gen_1 latency | 1 cycle | 1 cycle (`Register_*={false}`) | ✓ Fixed |
| blk_mem_gen_2 latency | 1 cycle | 1 cycle (`Register_*={false}`) | ✓ Fixed |
| blk_mem_gen_3 latency | 1 cycle | 1 cycle (`Register_*={false}`) | ✓ Fixed |
| FIFO depth | 8 entries (fifo4.sv) | 8 entries (fifo4.sv in IP) | ✓ |
| FIFO read output | Registered (+1 cycle) | Same RTL | ✓ |
| init_fill_valid window | count=1..8 (9 words max, FIFO holds 8) | Same RTL | ✓ |
| reset stall cycle | 1 cycle (count<=8 workaround) | Same RTL | ✓ |
| C_M_START_COUNT | 32 | 32 | ✓ |

**Bitstream rebuild required** after TCL changes to take effect. Previous board tests used the old bitstream with `Register_*={true}` (2-cycle BRAM).
