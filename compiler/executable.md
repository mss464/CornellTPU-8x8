# Mini-TPU Executable & TUDA Architecture

This document defines the current state of the Mini-TPU executable format and outlines the **TUDA** architectural vision for future development.

## 1. Current State: `.npz` Executables
The existing executable format (defined in [executable.py](file:///home/sk3463/main/projects/mini-tpu/compiler/executable.py)) is a compressed NumPy archive containing everything needed for verification.

### Bundle Contents:
- **`instructions`**: Raw 64-bit hardware instruction stream (`uint64`).
- **`memory_map`**: JSON mapping of buffer names to their static BRAM base addresses and sizes.
- **`inputs`**: Pre-defined test vectors loaded by the test harness.
- **`outputs`**: Pre-calculated reference arrays used to verify the TPU result.
- **`metadata`**: Versioning and developer context.

> [!CAUTION]
> The current format is "Monolithic". It forces reference data to be pre-calculated and bundled at compile time, which is not ideal for dynamic production workloads.

---

## 2. Future Vision: The TUDA Model
"TUDA" (Mini-TPU Unified Device Architecture) aims to align the software stack with the standard CUDA model.

### High-Level Refactoring Goals:
- **Clean Separation of Binaries**: Reference outputs should **not** be packaged with instructions. The `.npz` (or future `tuda` binary) should only contain the **Device Binaries** (code and static memory layout) and the **Host executable linked with the runtime library**.
- **Host Software Sovereignty**: The top-level application logic (Host Software) should be responsible for computing reference results dynamically. It should not be "baked into" the compiler output.
    - Implementation-side note: We will implement the tinytorch layer atop the TUDA layer. Reference could be computed at the tinytorch level, if that simplifies the implementation of TUDA.
- **Runtime as a Library**: The [runtime/](file:///home/sk3463/main/projects/mini-tpu/runtime/) should be refactored into a passive library. The host software calls runtime functions (e.g., `tudaMalloc`, `tudaMemcpy`, `tudaKernelLaunch`) to orchestrate execution.
    - Implementation-side note: We will migrate from Pynq to XRT and integrate with PJRT from OpenXLA
- **Unified "TUDA" Executable**: 
    - **Host Script**: A Python/C executable acting as the "Brain".
    - **Device Binary**: The compiled TPU kernels.
- **Dynamic Orchestration**: Memory should be managed dynamically by the host, and the test/validation flow should happen at runtime.

## 3. Developer Handover: Key Modules
- **[instructions.py](file:///home/sk3463/main/projects/mini-tpu/compiler/instructions.py)**: The ISA source of truth.
- **[compile.py](file:///home/sk3463/main/projects/mini-tpu/compiler/compile.py)**: The tracing and sequencing engine.
- **[runtime/](file:///home/sk3463/main/projects/mini-tpu/runtime/)**: The base for the future TUDA library.
- **[workflow/tools/](file:///home/sk3463/main/projects/mini-tpu/workflow/tools/)**: Current temporary bridge/harness logic.
