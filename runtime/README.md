# Mini-TPU Runtime

Execution orchestration, memory allocation, and hardware abstraction.

## Architecture

The runtime provides the Hardware Abstraction Layer (HAL) connecting host scripts to the physical Mini-TPU hardware. It exposes a unified `TpuDriver` interface and the **TUDA (Mini-TPU Unified Device Architecture)** API for orchestrating memory allocations and kernel execution.

The core interface is the unified `TpuDriver`. The factory `runtime.get_tpu_driver()` dynamically provides the correct backend driver:
- **Local (`pynq_host.py`)**: Sinks into `/dev/mem` and `pynq`'s `allocate` for direct physical hardware control. Used when running natively on the FPGA.
- **Remote (`rpc_client.py`)**: Used when the `MINITPU_HOST` variable is set. Serializes driver commands over a TCP socket to the remote FPGA board.

## Remote Execution Workflow

By natively executing host test programs on a desktop PC, `tuda.py` utilizes the RPC client transparently:
1. **Board Setup**: Administrator SSHes into the board and starts the bare-metal TCP server via `python3 runtime/rpc_server.py`.
2. **Desktop execution**: The user exports `MINITPU_HOST=192.168.x.x` locally.
3. **Transparent Execution**: When the desktop python script calls `tudaInit()`, TUDA loads the `RemoteTpuDriver`. All subsequent commands like `tudaMemcpy` pack their hex data and send it directly over TCP to shape the board's BRAM at line speed, and `tudaKernelLaunch` shoots the `.tpu_bin` payload directly to the hardware IP.

## Contents

| File | Description |
|------|-------------|
| `__init__.py` | Unified `get_tpu_driver()` factory routing |
| `tuda.py` | Mini-TPU Unified Device Architecture API |
| `allocator.py` | Memory region bump-allocator for TPU BRAM |
| `pynq_host.py` | PYNQ `/dev/mem` base driver (Local FPGA) |
| `rpc_server.py` | Bare-metal TCP server handling remote execution |
| `rpc_client.py` | Transparent TCP client routing Driver calls |
| `simulator.py` | Software simulation backend |

## Verification

The runtime host APIs and memory abstractions require logic validation independent of the physical TPU drivers (which would otherwise time out without real hardware attached). 

All standalone tests are located in `runtime/verification/`:

| Test Script | What It Verifies | How It Works |
|-------------|------------------|--------------|
| `test_tuda.py` | TUDA API & Allocator | Validates `tudaMalloc` addressing, bump-allocator constraints, and high-level abstraction logic by mocking out the low-level physical `TpuDriver`. |

To execute the automated runtime verification suite natively on the CPU:

```bash
cd runtime/verification
make all
```
