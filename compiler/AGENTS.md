# Mini-TPU Project Status

## 🚀 Current Architecture: Consolidated 4-File Core
The compiler has been streamlined into a minimal, high-performance core:
1. **`instructions.py`**: ISA and IR definition.
2. **`compile.py`**: Kernel tracing, program scheduling, bit-level encoding, and CLI for `.tu` to `.tpu_bin` compilation.
3. **`executable.py`**: `.tpu_bin` binary serialization and packaging.
4. **`main.py`**: CLI for trace generation (legacy).

## 🛠 Workflow & Layering
We follow a 4-stage software stack:
**Kernel** (`@kernel`) $\to$ **Program** (`Program`) $\to$ **Hardware Binary** (`ndarray`) $\to$ **Executable** (`TPUDeviceBinary`)

- **`demos/kernels/`**: Reusable kernel definitions (`.tu` files with `@kernel`).
- **`demos/programs/`**: Composition scripts for testing and applications.
- **`runtime/`**: Hardware abstraction and execution orchestration.

## ✅ Verification
- **Smoke Tests**: `compiler/verification/` passes all pipeline and ISA tests.
- **CLI Validation**: `main.py` generates correct symbolic traces for complex models (MLP).
- **SIMD Library**: Core SIMD operators are verified and ready for deployment.


