"""
Mini-TPU Compiler Package.

A 4-file streamlined compiler for the Mini-TPU architecture.
- instructions: ISA and IR facade.
- compile: Kernel tracing, program scheduling, and bit-level encoding.
- executable: Binary serialization (.npz).
- main: CLI entry point.
"""

from compiler.compile import kernel, Param, Program, KernelLauncher, load_program
from compiler.executable import TPUExecutable
from compiler import instructions

__all__ = [
    'kernel', 'Param', 'Program', 'KernelLauncher', 'load_program',
    'TPUExecutable', 'instructions'
]
