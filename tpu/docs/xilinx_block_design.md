# Xilinx Block Design Reference

> **Scope:** Detailed reference for the Vivado IPI block design that wraps the Mini-TPU IP.
> Extracted from PG021 (AXI DMA v7.1), UG1085 (Zynq UltraScale+ TRM), PG059 (AXI Interconnect), PG247 (SmartConnect).
> See [system.md](system.md) for the TPU register map and programming model.

---

## 1. Block Design Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Zynq UltraScale+ PS                        │
│  ┌──────────────────┐                    ┌────────────────────┐    │
│  │ M_AXI_HPM0_LPD   │───────┐           │  S_AXI_HP0_FPD     │    │
│  │ (ctrl master)     │       │           │  (DDR data slave)   │    │
│  └──────────────────┘       │           └──────▲─────────────┘    │
│  ┌──────────────────┐       │                  │                   │
│  │ pl_clk0 = 50 MHz │──┐    │                  │                   │
│  │ pl_resetn0        │  │    │                  │                   │
│  └──────────────────┘  │    │                  │                   │
└────────────────────────┼────┼──────────────────┼───────────────────┘
                         │    │                  │
                    ┌────▼────▼──┐          ┌────┴──────────┐
                    │proc_sys    │          │ AXI SmartConn  │
                    │reset_0     │          │ (axi_smc)      │
                    │            │          │ 2 SI / 1 MI    │
                    └──┬────┬───┘          └─▲────────▲────┘
         interconnect_ │    │ peripheral_    │        │
         aresetn       │    │ aresetn        │        │
                    ┌──▼────▼──────────┐     │        │
                    │ AXI Interconnect  │     │        │
                    │ (axi_ic_0)       │     │        │
                    │ 1 SI / 2 MI      │     │        │
                    └──┬───────────┬───┘     │        │
                  M00  │           │ M01     │        │
              ┌────────▼───┐   ┌──▼─────────┴──┐     │
              │ AXI DMA    │   │  Mini-TPU      │     │
              │ (axi_dma_0)│   │  (tpu_0)       │     │
              │            │   │                │     │
              │ S_AXI_LITE │   │ s00_axi (Lite) │     │
              │            │   │                │     │
              │ M_AXI_MM2S─┼───┼───────────────►│ S00 │
              │ M_AXI_S2MM─┼───┼───────────────►│ S01 │
              │            │   │                │ SMC  │
              │M_AXIS_MM2S ├──►│ s00_axis       │     │
              │S_AXIS_S2MM │◄──│ m00_axis       │     │
              └────────────┘   └────────────────┘     │
```

**Build script:** `tpu/scripts/build_bd_bitstream.tcl`
**Target part:** `xczu3eg-sbva484-1-i` (Ultra96-V2)

---

## 2. Zynq UltraScale+ PS Configuration

| Parameter | Value | Notes |
|-----------|-------|-------|
| PL clock (`pl_clk0`) | 50 MHz | `PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {50}` |
| Control master | `M_AXI_HPM0_LPD` | PS→PL AXI4 master, 32-bit, Low Power Domain |
| Data slave | `S_AXI_HP0_FPD` (`SAXIGP2`) | PL→PS DDR, Full Power Domain, **no cache coherency** |
| Other GP ports | All disabled | `M_AXI_GP0/1=0`, `S_AXI_GP0/3/4/5/6=0` |

### Cache Coherency

The HP port (`S_AXI_HP0_FPD`) connects directly to the DDR Memory Subsystem, **bypassing the CCI-400** cache coherent interconnect and the APU. This means:

- **Before MM2S (DMA reads DDR):** CPU must flush cache lines for the source buffer
- **Before CPU reads S2MM results:** CPU must invalidate cache lines for the destination buffer

PYNQ's `allocate()` returns physically contiguous, **non-cacheable** buffers — avoiding cache coherency issues entirely. This is why the Mini-TPU host driver uses `pynq.allocate()` for all DMA buffers.

**Alternative:** `S_AXI_HPC0_FPD` routes through CCI-400 for hardware coherency, but is not used in this design.

---

## 3. AXI DMA (PG021 v7.1) — Critical Protocol Reference

### Configuration

| Parameter | Value |
|-----------|-------|
| Scatter-Gather | Disabled (`c_include_sg {0}`) — Direct Register mode |
| MM2S (DDR→PL) | Enabled, 32-bit data width, burst=16 |
| S2MM (PL→DDR) | Enabled, 32-bit data width, burst=16 |
| Max burst size | 16 beats (auto-splits at 4KB AXI boundary) |

### S2MM TLAST Requirement — **The #1 Protocol Bug Source**

Every S2MM transfer completion depends on TLAST. The transfer ends when `tvalid`, `tready`, and `tlast` are all asserted on the same clock edge.

| Scenario | DMA Behavior |
|----------|-------------|
| TLAST never asserted | DMA sees incomplete packet → `DMAIntErr`, halts |
| TLAST early (before expected length) | S2MM stalls/errors; `DMAIntErr` may set |
| TLAST late (packet > DMA length reg) | `DMAIntErr` — incoming packet bigger than specified |
| TLAST at correct position | Normal completion, IOC interrupt generated |
| TLAST tied high (every beat) | First beat = last; remaining data lost |

**Post-TLAST:** `tvalid` must deassert on the same cycle `tlast` goes low. If `tvalid` stays high after `tlast`, the DMA interprets it as a new unconfigured transaction → stall.

**In this design:** `tpu_master_axi_stream.v` drives TLAST using a `beats_sent` counter. `M_AXIS_TKEEP` = all-ones whenever TVALID (required by S2MM).

### TKEEP Requirements

`s_axis_s2mm_tkeep` = 1 bit per byte of TDATA. For 32-bit data: `tkeep = 4'b1111` whenever `tvalid`.

### Direct Register Mode Register Map

**MM2S Channel (DDR → Stream):**

| Offset | Register | Description |
|--------|----------|-------------|
| `0x00` | MM2S_DMACR | Control (RS=bit0, Reset=bit2, IOC_IrqEn=bit12) |
| `0x04` | MM2S_DMASR | Status (Halted=bit0, Idle=bit1, DMAIntErr=bit4, IOC_Irq=bit12) |
| `0x18` | MM2S_SA | Source address (lower 32-bit) |
| `0x1C` | MM2S_SA_MSB | Source address (upper 32-bit) |
| `0x28` | MM2S_LENGTH | Transfer length in bytes — **writing initiates transfer** |

**S2MM Channel (Stream → DDR):**

| Offset | Register | Description |
|--------|----------|-------------|
| `0x30` | S2MM_DMACR | Control (same bit layout as MM2S) |
| `0x34` | S2MM_DMASR | Status (same bit layout as MM2S) |
| `0x48` | S2MM_DA | Destination address (lower 32-bit) |
| `0x4C` | S2MM_DA_MSB | Destination address (upper 32-bit) |
| `0x58` | S2MM_LENGTH | Buffer length in bytes — **writing initiates transfer** |

**Programming sequence:**
1. Set `RS=1` in DMACR (start channel)
2. Write source/destination address
3. Write transfer length → **this initiates the transfer**
4. Poll/wait for `IOC_Irq` in DMASR

### S2MM Status Register Error Bits (offset 0x34)

| Bit | Field | Meaning |
|-----|-------|---------|
| 0 | Halted | DMA channel halted |
| 1 | Idle | No active transfer |
| 4 | DMAIntErr | **Internal error** — TLAST missing, or packet > length register |
| 5 | DMASlvErr | AXI slave error on memory write |
| 6 | DMADecErr | Address decode error (unmapped address) |
| 12 | IOC_Irq | Interrupt on Complete (W1C) |
| 14 | Err_Irq | Interrupt on Error (W1C) |

**Error recovery:** Any error forces `DMACR.RS=0` (halt). Recovery: soft reset (`DMACR.Reset=1`, hold ~8 clocks).

**How PYNQ checks:** `recvchannel.wait()` polls DMASR for IOC_Irq or error bits. The `DMAIntErr` (bit 4) is the most common failure mode — caused by TLAST not aligning with the expected byte count.

---

## 4. AXI Interconnect (PG059 v2.1)

| Parameter | Value |
|-----------|-------|
| Instance | `axi_interconnect_0` |
| Topology | 1 SI / 2 MI |
| SI00 | ← `zynq_ps/M_AXI_HPM0_LPD` (PS control master) |
| MI00 | → `axi_dma_0/S_AXI_LITE` (DMA control registers) |
| MI01 | → `tpu_0/s00_axi` (TPU AXI-Lite registers) |

Routes PS control-plane writes to both the DMA control registers and the TPU register file. Protocol conversion from AXI4 → AXI4-Lite happens automatically.

---

## 5. AXI SmartConnect (PG247)

| Parameter | Value |
|-----------|-------|
| Instance | `axi_smc` |
| Topology | 2 SI / 1 MI |
| SI00 | ← `axi_dma_0/M_AXI_MM2S` (DMA read from DDR) |
| SI01 | ← `axi_dma_0/M_AXI_S2MM` (DMA write to DDR) |
| MI00 | → `zynq_ps/S_AXI_HP0_FPD` (DDR access) |

Merges both DMA memory ports into a single HP0 connection. SmartConnect provides MAMD arbitration — independent arbitration per destination on all 5 AXI channels, enabling higher throughput than AXI Interconnect.

---

## 6. Proc System Reset

| Instance | `proc_sys_reset_0` |
|----------|---------------------|
| Input | `zynq_ps/pl_resetn0` → `ext_reset_in` |
| Output 1 | `interconnect_aresetn` → AXI Interconnect + SmartConnect ARESETN |
| Output 2 | `peripheral_aresetn` → DMA `axi_resetn`, TPU `s00_axi_aresetn`, `s00_axis_aresetn`, `m00_axis_aresetn` |

Both outputs are **active-low** (asserted = 0 = reset). The Proc System Reset synchronizes the PS reset to the PL clock domain and generates stable, properly-timed reset signals.

---

## 7. Clock Tree

```
zynq_ps/pl_clk0 (50 MHz)
    ├── proc_sys_reset_0/slowest_sync_clk
    ├── axi_interconnect_0/ACLK, S00_ACLK, M00_ACLK, M01_ACLK
    ├── axi_smc/aclk
    ├── axi_dma_0/s_axi_lite_aclk, m_axi_mm2s_aclk, m_axi_s2mm_aclk
    ├── tpu_0/s00_axi_aclk, s00_axis_aclk, m00_axis_aclk
    ├── zynq_ps/maxihpm0_lpd_aclk  (feeds back to PS for LPD master port)
    └── zynq_ps/saxihp0_fpd_aclk   (feeds back to PS for HP0 slave port)
```

**Single clock domain.** All PL logic runs on `pl_clk0 = 50 MHz`. No clock domain crossing (CDC) logic needed. The PS internally handles the LPD/FPD clock domain differences.

---

## 8. Address Map

Addresses are assigned automatically by `assign_bd_address` in the TCL script. Typical assignment for Ultra96-V2:

| Master | Slave | Base Address | Range | Notes |
|--------|-------|-------------|-------|-------|
| `zynq_ps/Data` | `axi_dma_0/S_AXI_LITE/Reg` | Auto (e.g., `0x4040_0000`) | 64KB | DMA control registers |
| `zynq_ps/Data` | `tpu_0/s00_axi/reg0` | Auto (e.g., `0x4000_0000`) | 64KB | TPU AXI-Lite registers |
| `axi_dma_0/Data_MM2S` | `zynq_ps/SAXIGP2/HP0_DDR_LOW` | `0x0000_0000` | 2GB | DMA read from DDR |
| `axi_dma_0/Data_S2MM` | `zynq_ps/SAXIGP2/HP0_DDR_LOW` | `0x0000_0000` | 2GB | DMA write to DDR |

The exact PL-side base addresses depend on Vivado's address editor. Check the `.hwh` file (hardware handoff) for the actual values used in a given build. PYNQ reads the `.hwh` to auto-discover IP base addresses.

---

## 9. Known Issues and Xilinx AR References

1. **S2MM stall without TLAST** — If the PL stream source never asserts TLAST, the S2MM channel waits indefinitely. PYNQ's `recvchannel.wait()` will hang. Always ensure TLAST is asserted on the last beat.

2. **TKEEP must be all-valid** — If TKEEP has zero bits while TVALID is high, the DMA may write garbage bytes to DDR. The Mini-TPU master stream sets `TKEEP = 4'b1111` whenever `TVALID`.

3. **HP port cache coherency** — Data written by the DMA via HP0 is NOT visible to the CPU through cache. PYNQ handles this by using non-cacheable allocations. If using bare-metal or custom Linux drivers, explicit cache flush/invalidate is required.

4. **BRAM output register latency** — Xilinx Block RAM IP defaults can add an extra output register stage (2-cycle total latency vs 1-cycle). The Mini-TPU design requires 1-cycle latency (`Register_PortA/B_Output_of_Memory_Primitives {false}`). See [bram_specs.md](bram_specs.md) for details.

---

## References

- [AXI DMA v7.1 Product Guide (PG021)](https://docs.amd.com/r/en-US/pg021_axi_dma)
- [Zynq UltraScale+ Device TRM (UG1085)](https://docs.amd.com/r/en-US/ug1085-zynq-ultrascale-trm)
- [AXI Interconnect v2.1 (PG059)](https://docs.amd.com/r/en-US/pg059-axi-interconnect)
- [AXI SmartConnect (PG247)](https://docs.amd.com/r/en-US/pg247-smartconnect)
