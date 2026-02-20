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
