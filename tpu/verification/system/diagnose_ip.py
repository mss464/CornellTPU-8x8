import sys
import os
import json
from pynq import Overlay

def diagnose(bitstream=None):
    # 1. Load configuration
    config = {
        "bitstream": "minitpu.bit",
        "tpu_names": ["tpu_0", "tpu_top_0", "tpu"],
        "dma_names": ["axi_dma_0", "axi_dma", "dma"]
    }
    
    # Try multiple logical locations for the config
    for p in ["hw_config.json", "../tpu/hw_config.json", "/home/xilinx/tpu_deploy/hw_config.json"]:
        if os.path.exists(p):
            try:
                with open(p, 'r') as f:
                    config.update(json.load(f))
                print(f"Loaded config from {p}")
                break
            except Exception as e:
                print(f"Warning: Failed to parse {p}: {e}")

    if bitstream is None:
        bitstream = config.get("bitstream", "minitpu.bit")

    print(f"Loading overlay: {bitstream}")
    if not os.path.exists(bitstream):
        print(f"ERROR: Bitstream {bitstream} not found.")
        return

    try:
        ol = Overlay(bitstream)
        # Verification happens on download, but we check if we can access components
    except Exception as e:
        print(f"ERROR: Failed to load overlay: {e}")
        return

    all_ips = list(ol.ip_dict.keys())
    print(f"Detected IP blocks: {all_ips}")
    
    # 2. Check DMA
    dma_targets = config.get("dma_names", [])
    dma_found = [n for n in dma_targets if n in all_ips]
    
    if not dma_found:
        print("\nWARNING: No DMAs from config found. Falling back to fuzzy search.")
        dma_found = [k for k in all_ips if 'dma' in k.lower()]

    for name in dma_found:
        print(f"\n--- Checking DMA: {name} ---")
        try:
            dma = getattr(ol, name)
            # Read DMA Control Register (offset 0x00 for MM2S_DMACR)
            val = dma.mmio.read(0x00)
            print(f"  DMA Offset 0x00: 0x{val:08x}")
            if val != 0:
                 print("  SUCCESS: DMA is responding.")
            else:
                 print("  WARNING: DMA returned 0. Bus might be dead or reset active.")
        except Exception as e:
            print(f"  ERROR reading DMA {name}: {e}")
            
    # 3. Check TPU
    tpu_targets = config.get("tpu_names", [])
    tpu_found = [n for n in tpu_targets if n in all_ips]
    
    if not tpu_found:
        print("\nWARNING: No TPUs from config found. Falling back to fuzzy search.")
        tpu_found = [k for k in all_ips if 'tpu' in k.lower()]

    for name in tpu_found:
        print(f"\n--- Checking TPU: {name} ---")
        try:
            tpu = getattr(ol, name)
            # Read instr_ready (offset 0x04)
            val = tpu.mmio.read(0x04)
            print(f"  TPU Offset 0x04 (instr_ready): 0x{val:08x}")
            if val == 1:
                print("  SUCCESS: TPU is responding and ready.")
            else:
                print(f"  FAILURE: TPU returned 0x{val:08x}. Might be hung or in reset.")
        except Exception as e:
            print(f"  ERROR reading TPU {name}: {e}")

if __name__ == "__main__":
    target_bit = sys.argv[1] if len(sys.argv) > 1 else None
    diagnose(target_bit)
