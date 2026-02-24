# Mini-TPU: First-Principles Transformer Acceleration

A compact ML stack built from the bottom-up, from a Tensor Processing Unit implementation featuring a systolic array architecture, supporting FPGA prototyping and ASIC tapeout workflows.

## 🚀 quick Start: GPT-2 Demo

We have a full-scale **GPT-2 124M** demo that you can run on your CPU or through our hardware-fidelity systolic array simulation.

### 📁 Directory Structure
The demo files are located in `workflow/gpt2/`:
- `gpt2_benchmark.py`: Main inference script.
- `vocab.json` & `merges.txt`: GPT-2 tokenization data.
- `gpt2_weights.npz`: 124M parameter weights.

### 🏃 Running the Demos

1. **GEMM Performance Sweep**:
   Compare the speed of raw CPU (NumPy) against our software-emulated systolic array.
   ```bash
   make gemm
   ```

2. **Standard GPT-2 Inference**:
   ```bash
   make gpt2
   ```
   This uses the TinyTorch NumPy backend. You will be prompted to enter a custom text sequence and the number of tokens to generate.

3. **TPU-Simulated GPT-2**:
   ```bash
   make gpt2-tpusim
   ```
   This offloads Matrix Multiplications to a software-emulated **32x32 Systolic Array**.
   *Note: This is intended for studying hardware data flow and will be significantly slower than raw CPU.*

## 🧱 Repository Structure
- `tinytorch/`: Our custom ML framework built from scratch.
- `workflow/`: End-to-end applications and performance demos.
  - `gpt2/`: GPT-2 124M specific inference scripts and weights.
  - `kernels/`: Hand-optimized and simulated hardware kernels.
- `runtime/`: Driver and HAL logic for TPU interaction.
- `tpu/`: RTL implementation of the systolic array.

## License

MIT License