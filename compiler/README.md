# Mini-TPU Compiler

Instruction encoding, IR generation, and kernel development library.

## Software Layering
The Mini-TPU software stack follows a clear 4-stage transformation:
1. **Kernel** (`@kernel`): Python symbolic logic capturing hardware intent.
2. **Sequencing** (`Program`): The logical schedule that defines memory layout and kernel ordering.
3. **Binary** (`ndarray`): Raw 64-bit hardware instruction stream.
4. **Executable** (`TPUExecutable`): A packaged `.npz` archive containing instructions, test data, and memory maps.

## Component Map
| File | Layer | Description |
|------|-------|-------------|
| `instructions.py`| ISA | Symbolic operations and Low-level IR emission. |
| `compile.py` | Transform | Kernel tracing, Program composition, and Bit-encoding. |
| `executable.py` | Distribution | `TPUExecutable` (.npz) packaging and serialization. |
| `main.py` | CLI | Trace generator for model inspection. |

## Verification

Comprehensive smoke tests and CLI integration tests are located in `compiler/verification/`.
To run the verification suite:

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
Compile an existing model file to a symbolic trace:

```bash
python3 compiler/main.py compiler/kernels/mlp.py -o trace.txt
```
