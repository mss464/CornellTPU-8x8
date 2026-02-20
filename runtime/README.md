# Mini-TPU Runtime

Execution orchestration, memory allocation, and hardware abstraction.

## Architecture

```
TPUExecutor
    ├── allocator (memory layout)
    ├── TPUDevice (HAL interface)
    │   ├── PynqHost (FPGA)
    │   ├── Simulator (CPU)
    │   ├── XRT (Alveo/Versal)
    │   └── ASICGPIO (ASIC)
    └── TPUModule (compiled instructions)
```

The runtime is backend-agnostic; it delegates hardware interaction to HAL implementations.

## Contents

| File | Description |
|------|-------------|
| `allocator.py` | Memory region allocator for TPU BRAM |
| `executor.py` | High-level execution orchestrator |
| `device.py` | TPUDevice abstract interface (HAL boundary) |
| `pynq_host.py` | PYNQ overlay driver (current FPGA implementation) |
| `simulator.py` | Software simulation backend |
| `xrt.py` | XRT/OpenCL driver for Alveo/Versal |
| `asic_gpio.py` | GPIO protocol driver for taped-out ASIC |

## Verification

The runtime host APIs and memory abstractions require logic validation independent of the physical TPU drivers (which would otherwise time out without real hardware attached). 

All standalone tests are located in `runtime/verification/`:

| Test Script | What It Verifies | How It Works |
|-------------|------------------|--------------|
| `test_tuda.py` | TUDA API & Allocator | Validates `tudaMalloc` addressing, bump-allocator memory constraints, and high-level device abstraction logic by mocking out the low-level physical `TpuDriver`. |

To execute the automated runtime verification suite natively on the CPU:

```bash
cd runtime/verification
make all
```
