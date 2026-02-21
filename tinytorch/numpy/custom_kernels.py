import sys
import os
import numpy as np

# Ensure project root is in path to import the systolic simulator
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import the self-contained simulator
import systolic_tiled_matmul

def tiled_gemm(x1, x2):
    """
    Tiled Matrix Multiplication Bridge.
    Connects NumPy tensors to the pure Python hardware simulation.
    """
    a = np.asanyarray(x1)
    b = np.asanyarray(x2)

    # 1. Handle Batching/Broadcasting
    if a.ndim < 2 or b.ndim < 2:
        from . import _core
        return _core.matmul(x1, x2)

    batch_shape_a = a.shape[:-2]
    batch_shape_b = b.shape[:-2]
    
    try:
        dummy_a = np.empty(batch_shape_a)
        dummy_b = np.empty(batch_shape_b)
        batch_dims = np.broadcast(dummy_a, dummy_b).shape
    except ValueError:
        raise ValueError(f"Incompatible batch shapes: {batch_shape_a} and {batch_shape_b}")

    M, K = a.shape[-2:]
    K2, N = b.shape[-2:]
    
    # Results container
    res_shape = batch_dims + (M, N)
    res = np.zeros(res_shape, dtype=a.dtype)

    # 2. Iterate over Batch Dimensions
    for idx in np.ndindex(batch_dims):
        A_batch = np.broadcast_to(a, batch_dims + (M, K))[idx]
        B_batch = np.broadcast_to(b, batch_dims + (K, N))[idx]

        # Bridge: Convert NumPy to pure Python flat list
        A_pure = A_batch.flatten().tolist()
        B_pure = B_batch.flatten().tolist()

        # Call the standalone, self-contained hardware simulation
        res_pure = systolic_tiled_matmul.systolic_tiled_matmul(A_pure, B_pure, M, K, N)

        # Bridge: Convert back to NumPy
        res[idx] = np.array(res_pure).reshape(M, N)

    return res

def custom_gemm(x1, x2, out=None, **kwargs):
    """
    Custom GEMM interception for NumPy.
    Redirects to tiled_gemm for hardware simulation.
    """
    s1 = getattr(x1, 'shape', '?')
    s2 = getattr(x2, 'shape', '?')
    
    print(f"DEBUG: [Standalone Systolic Simulation] MatMul: {s1} @ {s2}")
    return tiled_gemm(x1, x2)
