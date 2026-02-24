# Mini-TPU Compiler

Instruction encoding, IR generation, and kernel development library.

## Software Layering
The Mini-TPU software stack follows a clear 4-stage transformation:
1. **Kernel** (`@kernel`): Python symbolic logic capturing hardware intent.
2. **Sequencing** (`Program`): The logical schedule that defines memory layout and kernel ordering.
3. **Binary** (`ndarray`): Raw 64-bit hardware instruction stream.
4. **Archive** (`TPUDeviceBinary`): A packaged `.tpu_bin` (NumPy `.npz`) containing instructions and memory layout.
5. **Executable** (`TPUExecutable`): A full distribution bundle (`.npz`) including instructions, memory map, and reference test data.

## Component Map
| File | Layer | Description |
|------|-------|-------------|
| `instructions.py`| ISA | Symbolic operations and Low-level IR emission. |
| `compile.py` | Transform | Kernel tracing, Program composition, and Bit-encoding. |
| `executable.py` | Distribution | Packaging and serialization for `.tpu_bin` and `.npz`. |
| `main.py` | CLI | Trace generator for model inspection. |

## Verification

The compiler logic is strictly validated offline without requiring physical TPU hardware. We test the translation of Python functions into raw instruction bits through the following automated suites in `compiler/verification/`:

| Test Script | What It Verifies | How It Works |
|-------------|------------------|--------------|
| `test_workflow.py` | E2E Pipeline | Validates the full sequence of tracing a dummy kernel, composing it into a program, tracking memory allocations, simulating codegen, and packaging it into an executable. |
| `test_isa.py` | ISA Codegen | Asserts that specific symbolic Python calls (e.g. `vload`, `matmul`) map to the exact intended 64-bit hardware binary encodings. | 
| `test_kernel.py` | AST / Python Logic | Validates the Python `@kernel` decorator, dynamic `Param` bindings and pointer arithmetic, instruction counts loops, and test launchers without hardware. |
| `test_device_binary.py` | Binary Format | Ensures that `.tpu_bin` device binaries can be successfully serialized and deserialized with intact instruction arrays and memory maps. |

To execute the automated verification suite:

```bash
cd compiler/verification
make all
```

## Usage

### 1. Library API
Build programs programmatically using the builder and instruction set:

```python
from compiler import Program, kernel, Param
from compiler.instructions import matmul, add, mem

@kernel
def my_op(W: Param, X: Param, Z: Param):
    matmul(W, X, Z)

prog = Program()
w_addr = prog.alloc("weights", 16)
prog.call(my_op, W=w_addr, ...)
prog.compile()
```

### 2. Compiler CLI
Compile a `.tu` file to a `.tpu_bin` device binary:

```bash
python3 compiler/compile.py demos/kernels/gemm.tu
```
