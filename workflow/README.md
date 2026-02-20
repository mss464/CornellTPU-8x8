# Mini TPU Usage

This directory contains tools and example TPU programs to use the Mini TPU.
It assumes you already have the hardware prepared as described in tpu/.

We use a unified test launcher that executes self-contained test executables (`.npz`).

### 1. Compile Test Executables
Run the program generators through the harness to create `.npz` files in `workflow/binaries/`:

```bash
# Generate all test executables
make executable-all

# Generate a specific executable manually
make executable PY=programs/comprehensive.py OUT=binaries/comprehensive.npz
```

### 2. Run Tests on Board
Use the `tpu_go_brrr` target to deploy and run a specific executable:

```bash
# Run comprehensive test
make tpu_go_brrr EXE=workflow/binaries/comprehensive.npz

# Run SIMD comparison
make tpu_go_brrr EXE=workflow/binaries/simd_comparison.npz

# Run SIMD Edge Cases
make tpu_go_brrr EXE=workflow/binaries/simd_edge_cases.npz
```

## Test Descriptions

- **comprehensive.npz**: Validates all instructions (Scalar & SIMD) with mixed workloads.
- **simd_comparison.npz**: Compares Scalar vs SIMD implementations of Add, Mul, ReLU.
- **simd_edge_cases.npz**: Tests boundary conditions (zeros, overflow, negative values).
- **pressure_scalar.npz / pressure_simd.npz**: Performance benchmarks.

## Adding New Tests

1. Create a generator in `programs/your_test.py` that defines a `define_program()` function:
   ```python
   import numpy as np
   from compiler.program import Program
   from compiler.kernel import kernel, Param

   def define_program():
       prog = Program()
       # ... setup program ...
       
       # ... define inputs/outputs ...
       inputs = { "a": np.array([...]) }
       outputs = { "z": np.array([...]) }
       
       return prog, inputs, outputs
   ```

2. Generate the executable using the harness:
   ```bash
   make executable PY=programs/your_test.py
   ```

3. Run launcher:
   ```bash
   python3 tools/test_launcher.py binaries/your_test.npz
   ```

## System Infrastructure

The `workflow/` directory serves as the integration and verification layer. While the `compiler/` package provides the tools to build instructions, `workflow/` provides the harness to validate them on-device.

### Responsibilities vs. Compiler
- **`workflow/tools/harness.py`**: Acts as the *Packaging Bridge*. It uses the `compiler.program.Program` object to generate raw instructions but also bundles them with **static memory maps** and **expected data** into a self-contained `.npz` executable. 
- **`workflow/tools/test_launcher.py`**: The *Hardware Runner*. Unlike the JIT-style `compiler.kernel.KernelLauncher`, this is designed for **Ahead-Of-Time (AOT)** verification of binaries. It handles DMA transfers of inputs, instruction loading, and automated numerical verification.

## Files
- `tools/harness.py`: Integration bridge that packages `Program` output into test executables.
- `tools/test_launcher.py`: AOT hardware test runner for `.npz` binaries.
- `programs/`: Source programs (generators) used for validation.
- `binaries/`: Compiled test artifacts ready for deployment.