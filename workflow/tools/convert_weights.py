import torch
import numpy as np
import os
import sys

def main():
    input_file = "pytorch_model.bin"
    output_file = "gpt2_weights.npz"

    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        sys.exit(1)

    print(f"Loading {input_file}...")
    # Load PyTorch state dict
    state_dict = torch.load(input_file, map_location="cpu", weights_only=True)

    print("Converting to NumPy format...")
    numpy_weights = {}
    for key, value in state_dict.items():
        numpy_weights[key] = value.numpy()

    print(f"Saving to {output_file}...")
    np.savez(output_file, **numpy_weights)
    print("Optimization: Saving as .npz complete.")

if __name__ == "__main__":
    main()
