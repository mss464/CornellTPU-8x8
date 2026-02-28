# BRAM Component Specifications

> **Scope:** Details for all four Block RAM IPs used in the TPU memory hierarchy. See [memory_hierarchy.md](memory_hierarchy.md) for the overview.

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
