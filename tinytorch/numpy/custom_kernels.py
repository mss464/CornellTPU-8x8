import sys
import os
import numpy as np
from pathlib import Path

# Ensure project root is in path to import the systolic simulator
project_root = str(Path(__file__).resolve().parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import the self-contained simulator
# Link to the workflow programs directory
kernels_dir = str(Path(project_root) / "demos" / "kernels")
if kernels_dir not in sys.path:
    sys.path.insert(0, kernels_dir)

try:
    import systolic_tiled_matmul
except ImportError as e:
    print(f"Failed to import systolic_tiled_matmul from {kernels_dir}: {e}")
    # Final fallback if still in root or elsewhere
    import systolic_tiled_matmul

def wrap_numpy_op(name, op):
    """
    Wraps a NumPy operation to print its signature if KERNEL_DEBUG is enabled.
    """
    def wrapper(*args, **kwargs):
        kernel_debug = os.environ.get("MINI_TPU_KERNEL_DEBUG") == "1"
        if kernel_debug:
            shapes = []
            for arg in args:
                if hasattr(arg, 'shape'):
                    shapes.append(str(arg.shape))
                elif isinstance(arg, (list, tuple)):
                    shapes.append(f"list/tuple(len={len(arg)})")
                else:
                    shapes.append(str(type(arg).__name__))
            
            shapes_str = ", ".join(shapes)
            print(f"    [CPU Numpy] {name}: {shapes_str}")
        
        return op(*args, **kwargs)
    
    # Proxy ufunc methods to avoid breaking internal NumPy reductions (like np.prod using multiply.reduce)
    for attr in ['reduce', 'accumulate', 'outer', 'at', 'reduceat']:
        if hasattr(op, attr):
            setattr(wrapper, attr, getattr(op, attr))
            
    return wrapper

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
    Redirects to tiled_gemm for hardware simulation ONLY IF DEBUG is enabled.
    """
    s1 = getattr(x1, 'shape', '?')
    s2 = getattr(x2, 'shape', '?')
    kernel_debug = os.environ.get("MINI_TPU_KERNEL_DEBUG") == "1"

    if os.environ.get("MINI_TPU_DEBUG") == "1":
        if kernel_debug:
            print(f"    [TPU Simulator] MatMul: {s1} @ {s2}")
        elif not kernel_debug and not os.environ.get("MINI_TPU_DEBUG_SILENT"):
            # Original behavior for DEBUG=1
            print(f"[TPU Simulator] MatMul: {s1} @ {s2}")
        return tiled_gemm(x1, x2)
    else:
        if kernel_debug:
            print(f"    [CPU Numpy] MatMul: {s1} @ {s2}")
        # Import original matmul to avoid recursion
        from . import _core
        return _core.matmul(x1, x2, out=out, **kwargs)
