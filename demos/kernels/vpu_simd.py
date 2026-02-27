"""
SIMD Vector Processing Unit kernels for Mini-TPU.

These kernels use the 8-lane SIMD VPU with vector registers (V0-V7)
for parallel execution, providing ~8x speedup over scalar operations.

Note: Imports must be inside kernel bodies to enable instruction capture
during compilation. The @kernel decorator patches tpu_txt functions temporarily.
"""

from compiler.compile import kernel, Param


@kernel
def vector_add_simd(A: Param, B: Param, C: Param, n: int = 8):
    """
    SIMD vector addition using 8-lane parallel execution.

    Computes: C[0:7] = A[0:7] + B[0:7] in parallel (1 cycle compute)

    Args:
        A: Address of first input vector (8 elements)
        B: Address of second input vector (8 elements)
        C: Address of output vector (8 elements)
        n: Number of elements (default 8, max 8 per vector register)

    Performance:
        Scalar VPU: 8 instructions × ~8 cycles = ~64 cycles
        SIMD VPU: 1 VLOAD + 1 VLOAD + 1 VADD + 1 VSTORE = ~30 cycles
        Speedup: ~2x overall (memory-bound), ~8x compute-bound
    """
    from compiler.instructions import vload, vadd, vstore

    # Load vectors into registers
    vload(0, A)         # V0 = A[0:7]
    vload(1, B)         # V1 = B[0:7]

    # Parallel add (8 elements in 1 cycle)
    vadd(2, 0, 1)       # V2 = V0 + V1

    # Store result
    vstore(2, C)        # C[0:7] = V2


@kernel
def vector_mul_simd(A: Param, B: Param, C: Param, n: int = 8):
    """
    SIMD vector multiplication using 8-lane parallel execution.

    Computes: C[0:7] = A[0:7] * B[0:7] in parallel (1 cycle compute)

    Args:
        A: Address of first input vector (8 elements)
        B: Address of second input vector (8 elements)
        C: Address of output vector (8 elements)
        n: Number of elements (default 8, max 8 per vector register)
    """
    from compiler.instructions import vload, vmul, vstore

    vload(0, A)         # V0 = A[0:7]
    vload(1, B)         # V1 = B[0:7]
    vmul(2, 0, 1)       # V2 = V0 * V1 (parallel)
    vstore(2, C)        # C[0:7] = V2


@kernel
def vector_relu_simd(X: Param, Y: Param, n: int = 8):
    """
    SIMD vector ReLU activation using 8-lane parallel execution.

    Computes: Y[0:7] = max(X[0:7], 0) in parallel (1 cycle compute)

    Args:
        X: Address of input vector (8 elements)
        Y: Address of output vector (8 elements)
        n: Number of elements (default 8, max 8 per vector register)

    Note: VRELU operation clips negative values to zero in hardware.
    """
    from compiler.instructions import vload, vrelu, vstore

    vload(0, X)         # V0 = X[0:7]
    vrelu(1, 0)         # V1 = ReLU(V0) (parallel)
    vstore(1, Y)        # Y[0:7] = V1


@kernel
def vector_scale_simd(X: Param, Scale: Param, Y: Param, n: int = 8):
    """
    SIMD vector scaling with scalar broadcast.

    Computes: Y[0:7] = X[0:7] * Scale[0] (broadcasts Scale[0] to all lanes)

    Args:
        X: Address of input vector (8 elements)
        Scale: Address of scalar value (single FP32 element)
        Y: Address of output vector (8 elements)
        n: Number of elements (default 8)

    Example use case: Learning rate scaling in neural networks
    """
    from compiler.instructions import vload, vmul, vstore

    vload(0, X)         # V0 = X[0:7]
    vload(1, Scale)     # V1 = [Scale[0], ...]
    vmul(2, 0, 1, scalar=True)  # V2 = V0 * V1[0] (scalar broadcast)
    vstore(2, Y)        # Y[0:7] = V2


@kernel
def vector_add_16_simd(A: Param, B: Param, C: Param):
    """
    SIMD vector addition for 16 elements (2 vector operations).

    Computes: C[0:15] = A[0:15] + B[0:15]

    Args:
        A: Address of first input vector (16 elements)
        B: Address of second input vector (16 elements)
        C: Address of output vector (16 elements)

    Performance:
        Scalar VPU: 16 instructions × ~8 cycles = ~128 cycles
        SIMD VPU: 4 VLOAD + 2 VADD + 2 VSTORE = ~60 cycles
        Speedup: ~2x overall
    """
    from compiler.instructions import vload, vadd, vstore

    # Process first 8 elements
    vload(0, A)         # V0 = A[0:7]
    vload(1, B)         # V1 = B[0:7]
    vadd(2, 0, 1)       # V2 = V0 + V1
    vstore(2, C)        # C[0:7] = V2

    # Process next 8 elements
    vload(3, A + 8)     # V3 = A[8:15]
    vload(4, B + 8)     # V4 = B[8:15]
    vadd(5, 3, 4)       # V5 = V3 + V4
    vstore(5, C + 8)    # C[8:15] = V5


@kernel
def fused_mlp_layer_simd(X: Param, W: Param, Bias: Param, Y: Param):
    """
    Fused MLP layer: Y = ReLU(X * W + Bias) using SIMD operations.

    Demonstrates chaining SIMD operations without intermediate BRAM writes.

    Args:
        X: Address of input vector (8 elements)
        W: Address of weight vector (8 elements)
        Bias: Address of bias vector (8 elements)
        Y: Address of output vector (8 elements)

    Performance:
        Scalar VPU: 24 instructions × ~8 cycles = ~192 cycles
        SIMD VPU: 6 instructions × ~8 cycles = ~48 cycles
        Speedup: ~4x
    """
    from compiler.instructions import vload, vmul, vadd, vrelu, vstore

    # Load inputs
    vload(0, X)         # V0 = X[0:7]
    vload(1, W)         # V1 = W[0:7]
    vload(2, Bias)      # V2 = Bias[0:7]

    # Compute: Z = X * W
    vmul(3, 0, 1)       # V3 = V0 * V1 (element-wise)

    # Add bias: Z = Z + Bias
    vadd(4, 3, 2)       # V4 = V3 + V2

    # Apply ReLU: Y = max(Z, 0)
    vrelu(5, 4)         # V5 = ReLU(V4)

    # Store result
    vstore(5, Y)        # Y[0:7] = V5
