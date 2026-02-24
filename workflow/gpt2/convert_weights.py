import torch
import numpy as np
import os
import sys

def convert():
    input_file = "pytorch_model.bin"
    output_file = "gpt2_weights.npz"

    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    print(f"Loading {input_file}...")
    # Load with map_location='cpu' as we don't need GPU for conversion
    state_dict = torch.load(input_file, map_location='cpu', weights_only=True)

    print(f"Converting to NumPy format...")
    weights_np = {k: v.numpy() for k, v in state_dict.items()}

    print(f"Saving to {output_file}...")
    np.savez(output_file, **weights_np)
    print("Optimization: Saving as .npz complete.")

if __name__ == "__main__":
    convert()
