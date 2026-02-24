# Mini TPU Usage

This directory contains tools and example TPU programs for using the Mini TPU.
It assumes you have already prepared the remote hardware using the unified RPC architecture.

## Execution Architecture

The test workflow relies on a unified remote execution abstraction.
Instead of pushing executables to the FPGA board, you run the host scripts **locally** on your PC. The runtime layer automatically detects `MINITPU_HOST` and forwards memory and compute operations to the remote target's RPC server.

**Pre-requisite:**
1. Start the RPC Server on the FPGA Board (`runtime/rpc_server.py`).
2. Export the board's IP address:
```bash
export MINITPU_HOST=192.168.x.x
```
3. Your compiled `.tpubin` files must be prepared offline in `demos/binaries/`.

## Running Tests

Use the local `Make` targets to compile the instructions offline and run the host verification programs against the remote TPU:

```bash
# Compile all programs to `.tpubin`
make compile-tests

# Run comprehensive test
make board-comprehensive

# Run SIMD Edge Cases
make board-edge-cases
```

Alternatively, you can run the python programs directly. Use `--compile` to build the required `.tpubin` offline payload, and simply run the script to execute it on the host and forward memory/launch instructions to the `MINITPU_HOST`.

```bash
python3 programs/comprehensive.py --compile
python3 programs/comprehensive.py
```

## Creating New Tests

1. Create a standard Python script in `programs/your_test.py`.
2. Use the `Program.compile()` to write an offline `.tpubin`.
3. Use the TUDA host API (`tudaMemcpy`, `tudaKernelLaunch`) directly in your code to inject dependencies, evaluate the remote device computation, and bring results back to the host for verification against NumPy!