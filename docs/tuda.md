# TUDA (Mini-TPU Unified Device Architecture)

TUDA is the host-side software stack designed to explicitly decouple generic hardware instruction logic (device kernels) from mathematical reference computation and orchestration (host software). 

TUDA is designed bottom-up from our Mini-TPU hardware architecture, to bridge with the upper software layers (OpenXLA + PyTorch / tinytorch).

## Architecture

1. **Host-Side (CPU)**: Runs a standard Python execution environment on the board (e.g. `pynq` ARM processor). This logic uses the `@host` decorator.
2. **Device-Side (TPU)**: Programs statically compiled ahead-of-time (or Just-In-Time compiled dynamically in Phase 2) into pure `.tpu_bin` executables containing only instructions and memory maps. Designed primarily in pure Python using the `@kernel` decorator.

## Workflow

1. A device kernel is written using the Mini-TPU compiler libraries.
2. `compiler/compile.py` translates the kernel down to a `.tpu_bin` executable file.
3. The board application invokes `tudaInit()`, allocates TPU block RAMs using `tudaMalloc()`, copies input tensors using `tudaMemcpy()`, and dispatches the execution logic by passing the `.tpu_bin` file directly down to `tudaKernelLaunch()`.

### Example

```python
from runtime.tuda import host, tudaInit, tudaMalloc, tudaMemcpy, tudaKernelLaunch

# Initialize hardware Driver runtime
tudaInit()

# Explicitly allocate block RAM
tudaMalloc("weight_matrix", 16) # Size in words
tudaMalloc("input_vector", 16)

# Provide NumPy Arrays from Host CPU memory into Device memory
tudaMemcpy(0, numpy_array_weights, "HostToDevice")
tudaMemcpy(16, numpy_array_inputs, "HostToDevice")

# Stream the static TPU executable block and compute
tudaKernelLaunch("gemm.tpu_bin")

# Fetch computed TPU output back into Host NumPy CPU memory
computed_result = tudaMemcpy(32, 16, "DeviceToHost") # Start ADDR, WORDS to read
```

## Known Limitations and Next Steps

- **Static Memory Mapping**: Currently `tudaKernelLaunch` runs pre-compiled binaries that expect exact base memory addresses (e.g., 0, 16, 32). If `tudaMalloc()` yields different block regions during runtime, the operations will fail.
  - *Phase 2 mitigation*: Build a Dynamic Relocation mechanism inside the binary or compiler to link actual runtime memory regions into the kernel dynamically right before stream writing.
- **NumPy Assumption**: Currently, the `tudaMemcpy` function implicitly casts and assumes Host arrays strictly exist as multi-dimensional `numpy.ndarray` objects. Memory semantics do not yet natively support PyTorch Tensors or native Python Lists out of the box without prior manual translation by the developer.  
- **Hardware Fallbacks / Mocks**: Current testing allows offline validation using mock class injections for API assertions. Future work should build a cycle-accurate or ISA-level TPU software emulator to prevent real hardware execution bottlenecks during initial CI tests.
