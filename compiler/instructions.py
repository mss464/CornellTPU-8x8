"""
Mini-TPU Instruction Set Architecture (ISA) & IR.

This module defines the Intermediate Representation (IR) for the TPU. It provides 
the high-level operations (matmul, add, etc.) used to build kernels, as well 
as the global instruction log used during the tracing phase.

Architecture:
1. High-level API (add, matmul): Mirrored after common tensor libraries.
2. Low-level IR (vadd, vload): Direct mappings to hardware instructions.
3. Memory Management: Integrated access to the TPU scratchpad allocator.
"""

import numpy as np
from runtime.allocator import allocator as mem

# Global state for instruction tracing
_instruction_log = []

def log_instruction(op: str, *operands):
    """Log a symbolic instruction to the global trace."""
    instruction = f"{op} {', '.join(map(str, operands))}"
    _instruction_log.append(instruction)

def get_instruction_log():
    """Retrieve the current trace of symbolic instructions."""
    return _instruction_log

def clear_instruction_log():
    """Clear the trace for a fresh compilation/run."""
    _instruction_log.clear()

# ============================================================================
# Scalar VPU Operations (Legacy loop-compatible)
# ============================================================================

def add(X: int, Y: int, Z: int):
    """*Z = *X + *Y (Scalar)"""
    log_instruction("add", X, Y, Z)

def sub(X: int, Y: int, Z: int):
    """*Z = *X - *Y (Scalar)"""
    log_instruction("sub", X, Y, Z)

def mul(X: int, Y: int, Z: int):
    """*Z = (*X) * (*Y) (Scalar)"""
    log_instruction("mul", X, Y, Z)

def relu(X: int, Zero_addr: int, Y: int):
    """*Y = max(*X, 0) (Scalar)"""
    log_instruction("relu", X, Zero_addr, Y)

def relu_derivative(X: int, Zero_addr: int, Y: int):
    """*Y = 1.0 if *X > 0 else 0.0 (Scalar)"""
    log_instruction("relu_derivative", X, Zero_addr, Y)

# ============================================================================
# SIMD VPU Operations (8-lane Parallel)
# ============================================================================

def vload(vreg: int, addr: int):
    """Load 8 FP32 words into vector register vreg (0-7)."""
    log_instruction("vload", vreg, addr)

def vstore(vreg: int, addr: int):
    """Store 8 FP32 words from vector register vreg (0-7) to BRAM."""
    log_instruction("vstore", vreg, addr)

def vadd(vreg_dst: int, vreg_a: int, vreg_b: int, scalar: bool = False):
    """Parallel vector addition. If scalar=True, broadcasts vreg_b[0]."""
    log_instruction("vadd", vreg_dst, vreg_a, vreg_b, scalar)

def vsub(vreg_dst: int, vreg_a: int, vreg_b: int, scalar: bool = False):
    """Parallel vector subtraction."""
    log_instruction("vsub", vreg_dst, vreg_a, vreg_b, scalar)

def vmul(vreg_dst: int, vreg_a: int, vreg_b: int, scalar: bool = False):
    """Parallel vector multiplication."""
    log_instruction("vmul", vreg_dst, vreg_a, vreg_b, scalar)

def vrelu(vreg_dst: int, vreg_src: int):
    """Parallel vector ReLU."""
    log_instruction("vrelu", vreg_dst, vreg_src)

def vmax(vreg_dst: int, vreg_a: int, vreg_b: int):
    """Parallel vector Maximum."""
    log_instruction("vmax", vreg_dst, vreg_a, vreg_b)

def vmin(vreg_dst: int, vreg_a: int, vreg_b: int):
    """Parallel vector Minimum."""
    log_instruction("vmin", vreg_dst, vreg_a, vreg_b)

# ============================================================================
# Systolic Array & Memory Control
# ============================================================================

def matmul(W: int, X: int, Z: int, m: int = 4):
    """
    Systolic array matrix multiplication.
    Computes Z = X @ W^T for mxm matrices.
    """
    log_instruction("matmul", W, X, Z)

def load(start_addr, data):
    """
    Host-to-TPU memory transfer.
    Encodes data as a literal list in the trace for simulation/loading.
    """
    if not isinstance(data, np.ndarray):
        data = np.array(data, dtype=np.float32)
    flat = data.astype(np.float32).flatten()
    log_instruction("load", start_addr, flat.size, flat.tolist())

def store(start_addr, length, name: str):
    """
    TPU-to-Host memory read request.
    Identifies a region to be verified or logged after compute.
    """
    log_instruction("store", start_addr, length, name)

__all__ = [
    "mem", "add", "sub", "mul", "relu", "relu_derivative",
    "vload", "vstore", "vadd", "vsub", "vmul", "vrelu", "vmax", "vmin",
    "matmul", "load", "store", "get_instruction_log", "clear_instruction_log"
]
