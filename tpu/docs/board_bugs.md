# Board Bug Analysis — Read DMA Corruption

> **Scope:** Root cause analysis of DMA read corruption observed on the Ultra96-V2 board. See [data_movement.md](data_movement.md) for the Mode 2 read path architecture.

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

The write path (`tpu_slave_axi_stream.v`) has the same IDLE→WRITE_FIFO reset stall pattern documented in CLAUDE.md Design Pitfall §1. The slave stream's `write_pointer_stream` fires from reset on the first WRITE_FIFO cycle because `reset=1` from IDLE. The BRAM write (`wea`) is already firing. Fix: gate `wea` (= `data_write_en`) on the fifo_wren handshake, OR ensure `write_pointer_stream` is already incremented by the time the first BRAM write fires.

Simplest correct fix: make `data_write_en` (and thus `wea`) only assert when `fifo_wren` is true (i.e., require AXI handshake before allowing BRAM write). Currently `wea = data_write_en` fires independent of TVALID/TREADY.

**Fix A — slave stream write pointer stall** (`tpu_slave_axi_stream.v`):
Apply the same pattern as the `reset <= 1'b0` fix already in place on line 123. The `write_pointer_stream` reset block (in Block 2, guarded by `if(!ARESETN || reset)`) fires at the first WRITE_FIFO cycle because `reset=1` from IDLE. The BRAM write (`wea`) is already firing. Fix: gate `wea` (= `data_write_en`) on the fifo_wren handshake, OR ensure `write_pointer_stream` is already incremented by the time the first BRAM write fires.

Simplest correct fix: make `data_write_en` (and thus `wea`) only assert when `fifo_wren` is true (i.e., require AXI handshake before allowing BRAM write). Currently `wea = data_write_en` fires independent of TVALID/TREADY.

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
