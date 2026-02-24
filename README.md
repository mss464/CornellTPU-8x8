# Mini-TPU

A compact ML stack built from the bottom-up, from a Tensor Processing Unit implementation featuring a systolic array architecture, supporting FPGA prototyping and ASIC tapeout workflows.

## Quickstart 1. 🚀 Hardware Kernel Demo: GEMM
Benchmark the core of the TPU—the **32x32 Systolic Array**—against highly optimized CPU BLAS (NumPy).

```bash
make gemm
```
This performs a performance sweep across various matrix sizes.

## Quickstart 2. 🧠 End-to-End Application: GPT-2 124M
Run a full GPT-2 model using our handcrafted autograd engine. We support both high-speed CPU inference and bit-accurate hardware simulation.

### 🛠 1. Setup
First, download the model weights and assets (tokenizers, configs). This targets the HuggingFace repository and handles the PyTorch-to-NumPy conversion automatically.
```bash
make setup
```

### 🏃 2. Running Inference
- **Standard (NumPy)**: Fast CPU inference.
  ```bash
  make gpt2
  ```
- **TPU-Simulated**: Hardware-fidelity 32x32 systolic array execution.
  ```bash
  make gpt2-tpusim
  ```

## 🧱 Repository Structure
- `tinytorch/`: Our custom ML framework built from scratch.
- `workflow/`: End-to-end applications and performance demos.
  - `gpt2/`: GPT-2 124M specific inference scripts and weights.
  - `kernels/`: Hand-optimized and simulated hardware kernels.
- `runtime/`: Driver and HAL logic for TPU interaction.
- `compiler/`: High-level compiler for TPU assembly.
- `tpu/`: RTL implementation of the systolic array (FPGA/ASIC).

## License

MIT License