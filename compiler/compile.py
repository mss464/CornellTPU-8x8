"""
Mini-TPU Compilation Engine.

This module provides the core transformation logic to convert Python-defined 
kernels and programs into hardware-compatible 64-bit instruction streams.

Workflow Overview:
1. Define a @kernel: A Python function using symbolic logic.
2. Trace the Kernel: Implicitly captured by the @kernel decorator.
3. Compose a Program: Allocate memory and schedule kernel calls with concrete addresses.
4. Encode to Binary: Resolve symbolic addresses and encode opcodes into hardware words.

Example:
---------
    from compiler.instructions import vadd, vload, vstore
    from compiler import Program, kernel, Param

    # 1. Define Kernel
    @kernel
    def my_kernel(A: Param, B: Param, C: Param):
        vload(0, A)
        vload(1, B)
        vadd(2, 0, 1)
        vstore(2, C)

    # 2. Compose Program
    prog = Program()
    addr_a = prog.alloc("input_a", 8)
    addr_b = prog.alloc("input_b", 8)
    addr_c = prog.alloc("output_c", 8)

    prog.call(my_kernel, A=addr_a, B=addr_b, C=addr_c)

    # 3. Generate Binary
    binary = prog.compile()  # Returns np.ndarray[uint64]
"""

from __future__ import annotations
import inspect
import functools
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable, Union
from runtime.allocator import MemoryAllocator

# ============================================================================
# Architectural Constraints & Codegen (Opcodes must match RTL)
# ============================================================================

ADDR_MAX = (1 << 13) - 1

OPCODES_VPU = {
    'add': 0, 'sub': 1, 'relu': 2, 'mul': 3, 'relu_derivative': 4,
}

OPCODES_VCOMPUTE = {
    'vadd': 0, 'vsub': 1, 'vmul': 2, 'vrelu': 3, 'vmax': 4, 'vmin': 5,
}

def encode_vpu(op: str, addr_a: int, addr_b: int, addr_out: int, addr_const: int = 0) -> int:
    """Format: [63:60=0][59:56=op][55:42=a][41:28=b][27:14=out][13:0=const]"""
    opcode = OPCODES_VPU[op]
    word = (opcode & 0xF) << 56
    word |= (addr_a & 0x3FFF) << 42
    word |= (addr_b & 0x3FFF) << 28
    word |= (addr_out & 0x3FFF) << 14
    word |= (addr_const & 0x3FFF)
    return word

def encode_systolic(addr_w: int, addr_x: int, addr_z: int, length: int) -> int:
    """Format: [63:60=1][59:46=w][45:32=x][31:18=z][17:0=len]"""
    word = (1 << 60)
    word |= (addr_w & 0x3FFF) << 46
    word |= (addr_x & 0x3FFF) << 32
    word |= (addr_z & 0x3FFF) << 18
    word |= (length & 0x3FFFF)
    return word

def encode_vload(vreg: int, addr: int) -> int:
    """Format: [63:60=2][59:56=vreg][55:0=addr]"""
    word = (2 << 60)
    word |= (vreg & 0x7) << 56
    word |= (addr & 0x3FFF)
    return word

def encode_vstore(vreg: int, addr: int) -> int:
    """Format: [63:60=3][59:56=vreg][55:0=addr]"""
    word = (3 << 60)
    word |= (vreg & 0x7) << 56
    word |= (addr & 0x3FFF)
    return word

def encode_vcompute(op: str, vdst: int, va: int, vb: int, scalar: bool = False) -> int:
    """Format: [63:60=4][59:56=vop][55:52=dst][51:48=a][47:44=b][43=scalar]"""
    vop = OPCODES_VCOMPUTE[op]
    word = (4 << 60)
    word |= (vop & 0xF) << 56
    word |= (vdst & 0xF) << 52
    word |= (va & 0xF) << 48
    word |= (vb & 0xF) << 44
    if scalar: word |= (1 << 43)
    return word

def encode_halt() -> int:
    """Opcode 15: Stop Hardware execution."""
    return (0xF << 60)

# ============================================================================
# Symbolic Primitives
# ============================================================================

class Param:
    """Symbolic address that resolves to a concrete word-address at launch."""
    def __init__(self, name: str, offset: int = 0):
        self.name = name
        self.offset = offset

    def __repr__(self):
        if self.offset == 0: return f"Param('{self.name}')"
        sign = "+" if self.offset > 0 else "-"
        return f"Param('{self.name}') {sign} {abs(self.offset)}"

    def __add__(self, other: int) -> Param:
        return Param(self.name, self.offset + other)

    def __radd__(self, other: int) -> Param:
        return self.__add__(other)

    def __sub__(self, other: int) -> Param:
        return Param(self.name, self.offset - other)

    def resolve(self, bindings: Dict[str, int]) -> int:
        if self.name not in bindings:
            raise ValueError(f"Param '{self.name}' not bound to an address")
        addr = bindings[self.name] + self.offset
        if not (0 <= addr <= ADDR_MAX):
            raise ValueError(f"Address {addr} (for {self.name}+{self.offset}) out of range")
        return addr

@dataclass
class SymbolicInstruction:
    """Templatized instruction with symbolic placeholders."""
    op: str
    operands: tuple

    def resolve(self, bindings: Dict[str, int]) -> int:
        vals = [o.resolve(bindings) if isinstance(o, Param) else o for o in self.operands]
        if self.op == "matmul": return encode_systolic(*vals)
        if self.op == "vload": return encode_vload(*vals)
        if self.op == "vstore": return encode_vstore(*vals)
        if self.op == "vrelu": return encode_vcompute(self.op, vals[0], vals[1], 0, False)
        if self.op in ("vmax", "vmin"): return encode_vcompute(self.op, *vals, False)
        if self.op in OPCODES_VCOMPUTE: return encode_vcompute(self.op, *vals)
        if self.op in OPCODES_VPU: return encode_vpu(self.op, *vals)
        raise ValueError(f"Unknown Op: {self.op}")

# ============================================================================
# Tracing Engine
# ============================================================================

class InstructionCapture:
    """Context manager for tracing IR function calls into SymbolicInstructions."""
    def __init__(self, fn_to_patch=None):
        self.captured: List[SymbolicInstruction] = []
        self._originals = {}
        self._fn_to_patch = fn_to_patch
        self._patched_globals = {}

    def __enter__(self):
        import compiler.instructions as ir
        ops = ['matmul','add','sub','mul','relu','relu_derivative','vload','vstore','vadd', 'vsub','vmul','vrelu','vmax','vmin']
        for op in ops:
            self._originals[op] = getattr(ir, op)
            setattr(ir, op, self._wrap(op))
            
            if self._fn_to_patch and op in self._fn_to_patch.__globals__:
                self._patched_globals[op] = self._fn_to_patch.__globals__[op]
                self._fn_to_patch.__globals__[op] = getattr(ir, op)

        return self

    def __exit__(self, t, v, tb):
        import compiler.instructions as ir
        for op, fn in self._originals.items():
            setattr(ir, op, fn)
            
        if self._fn_to_patch:
            for op, fn in self._patched_globals.items():
                self._fn_to_patch.__globals__[op] = fn

    def _wrap(self, op: str):
        def fn(*args, **kwargs):
            if op == 'matmul':
                operands = (args[0], args[1], args[2], (kwargs.get('m', 4) if len(args) < 4 else args[3])**2)
            elif op in ('vadd', 'vsub', 'vmul'):
                operands = (args[0], args[1], args[2], (kwargs.get('scalar', False) if len(args) < 4 else args[3]))
            else:
                operands = args
            self.captured.append(SymbolicInstruction(op, operands))
        return fn

@dataclass
class CompiledKernel:
    name: str
    params: List[str]
    instructions: List[SymbolicInstruction] = field(default_factory=list)

    def resolve(self, bindings: Dict[str, int]) -> np.ndarray:
        missing = [p for p in self.params if p not in bindings]
        if missing:
            raise ValueError(f"Missing bindings for parameters: {missing}")
        return np.array([i.resolve(bindings) for i in self.instructions], dtype=np.uint64)

class KernelFunction:
    def __init__(self, fn: Callable):
        self._fn = fn
        functools.update_wrapper(self, fn)
    def __call__(self, *args, **kwargs): return self._fn(*args, **kwargs)
    def compile(self) -> CompiledKernel:
        sig = inspect.signature(self._fn)
        names = [n for n, p in sig.parameters.items() if p.annotation == Param or p.default is inspect.Parameter.empty]
        with InstructionCapture(self._fn) as capture:
            self._fn(**{n: Param(n) for n in names})
        return CompiledKernel(self._fn.__name__, names, capture.captured)

def kernel(fn: Callable) -> KernelFunction:
    """Decorator to transform a Python function into a traceable TPU Kernel."""
    return KernelFunction(fn)

# ============================================================================
# Program Scheduling
# ============================================================================

@dataclass
class KernelCall:
    kernel: CompiledKernel
    bindings: Dict[str, int]

class Program:
    """Entry point for composing complete, executable programs."""
    def __init__(self, allocator: MemoryAllocator = None):
        self.allocator = allocator or MemoryAllocator()
        self.calls: List[KernelCall] = []
        self._cache: Dict[str, CompiledKernel] = {}

    def alloc(self, name: str, size: int) -> int:
        return self.allocator.alloc(name, size)

    def call(self, k: Union[KernelFunction, CompiledKernel], **bindings: int):
        if isinstance(k, KernelFunction):
            if k.__name__ not in self._cache: self._cache[k.__name__] = k.compile()
            k = self._cache[k.__name__]
        self.calls.append(KernelCall(k, bindings))

    def get_memory_map(self) -> Dict[str, Dict[str, int]]:
        return {k: {"addr": v[0], "size": v[1]} for k, v in self.allocator.memory_map.items()}

    def compile(self) -> np.ndarray:
        binary = [c.kernel.resolve(c.bindings) for c in self.calls]
        if not binary: return np.array([encode_halt()], dtype=np.uint64)
        return np.concatenate(binary + [np.array([encode_halt()], dtype=np.uint64)])

# ============================================================================
# Utilities
# ============================================================================

class KernelLauncher:
    """Direct-to-hardware launcher (JIT style) for rapid validation."""
    def __init__(self, driver): self.driver = driver
    def launch(self, k: CompiledKernel, **bindings: int):
        self.driver.write_instructions(np.concatenate([k.resolve(bindings), [encode_halt()]]))
        self.driver.compute()

    def launch_batch(self, batch: List[tuple]):
        """Launch multiple (kernel, bindings) pairs in a single driver session."""
        all_instr = []
        for k, bindings in batch:
            all_instr.append(k.resolve(bindings))
        full_stream = np.concatenate(all_instr + [np.array([encode_halt()], dtype=np.uint64)])
        self.driver.write_instructions(full_stream)
        self.driver.compute()
        return sum(len(k.instructions) for k, _ in batch)

def load_program(path: Union[str, Path]) -> np.ndarray:
    """Load a compiled instruction stream (.npy or .hex)."""
    p = Path(path)
    if p.suffix == '.npy': return np.load(p)
    return np.array([int(line, 16) for line in open(p) if line.strip() and not line.startswith('#')], dtype=np.uint64)

if __name__ == "__main__":
    import sys
    import argparse
    import importlib.util
    from compiler.executable import TPUDeviceBinary

    parser = argparse.ArgumentParser(description="Mini-TPU Device Binary Compiler")
    parser.add_argument("program_py", help="Path to the kernel definition script (.tu or .py)")
    parser.add_argument("-o", "--output", help="Output path for the generated binary (.tpu_bin)")
    args = parser.parse_args()

    program_path = Path(args.program_py).resolve()
    if not program_path.exists():
        print(f"Error: Script not found: {program_path}")
        sys.exit(1)

    # Add project root and script path to sys.path
    project_root = program_path.parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    if str(program_path.parent) not in sys.path:
        sys.path.insert(0, str(program_path.parent))

    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader("program_module", str(program_path))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)

    if hasattr(module, 'define_program'):
        result = module.define_program()
        # Handle both old (prog, inputs, outputs) and new (prog) formats safely
        prog = result[0] if isinstance(result, tuple) else result
        
        if args.output:
            out_path = Path(args.output)
            if out_path.suffix != '.tpu_bin':
                out_path = out_path / f"{program_path.stem}.tpu_bin"
        else:
            out_path = Path("workflow/binaries") / f"{program_path.stem}.tpu_bin"
            
        memory_map = prog.get_memory_map()
        binary = TPUDeviceBinary(instructions=prog.compile(), memory_map=memory_map)
        binary.save(out_path, verbose=True)
    else:
        print(f"Error: Script {program_path.name} must define 'define_program()'")
        sys.exit(1)
