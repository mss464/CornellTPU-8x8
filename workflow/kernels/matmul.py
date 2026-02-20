"""
Matrix multiplication kernels for Mini-TPU.

Note: Imports must be inside kernel bodies to enable instruction capture
during compilation. The @kernel decorator patches tpu_txt functions temporarily.
"""

from compiler.compile import kernel, Param


@kernel
def matmul_4x4(W: Param, X: Param, Z: Param):
    """
    4x4 matrix multiplication kernel.

    Computes: Z = X @ W^T

    Args:
        W: Address of 4x4 weight matrix (16 words)
        X: Address of 4x4 input matrix (16 words)
        Z: Address of 4x4 output matrix (16 words)
    """
    from compiler.instructions import matmul
    matmul(W, X, Z, m=4)


@kernel
def matmul_8x8_tiled(W: Param, X: Param, Z: Param, temp: Param):
    """
    8x8 tiled matrix multiplication using 2x2x2 tile decomposition.

    Computes: Z = X @ W^T

    Both matrices must be stored in tile-major order (4x4 tiles).

    Args:
        W: Address of 8x8 weight matrix in tile-major (64 words)
        X: Address of 8x8 input matrix in tile-major (64 words)
        Z: Address of 8x8 output matrix in tile-major (64 words)
        temp: Address of temporary tile storage (16 words)
    """
    from compiler.instructions import matmul, add
    t2 = 16  # tile size squared (4x4 = 16)

    # Z[i,j] = sum_k(X[i,k] @ W[j,k]^T)
    for i in range(2):
        for j in range(2):
            Z_tile = Z + (i * 2 + j) * t2
            for k in range(2):
                X_tile = X + (i * 2 + k) * t2
                W_tile = W + (j * 2 + k) * t2

                if k == 0:
                    # First: Z[i,j] = X[i,k] @ W[j,k]^T
                    matmul(W_tile, X_tile, Z_tile, m=4)
                else:
                    # Accumulate: Z[i,j] += X[i,k] @ W[j,k]^T
                    matmul(W_tile, X_tile, temp, m=4)
                    for elem in range(t2):
                        add(Z_tile + elem, temp + elem, Z_tile + elem)


def tiled_matmul(W_addr, X_addr, Z_addr, M, N, K, tile_size=4, temp_addr=None, allocator=None):
    """
    Performs tiled matrix multiplication for matrices larger than hardware tile size.

    Computes Z = X @ W^T where:
    - X is M x K matrix at X_addr
    - W is N x K matrix at W_addr
    - Z is M x N matrix at Z_addr

    Args:
        W_addr: Base address of weight matrix W (N x K, row-major, stored as tiles)
        X_addr: Base address of input matrix X (M x K, row-major, stored as tiles)
        Z_addr: Base address of output matrix Z (M x N, row-major, stored as tiles)
        M: Number of rows in X and Z
        N: Number of rows in W (columns in Z)
        K: Number of columns in X and W
        tile_size: Hardware tile size (default 4)
        temp_addr: Address for temporary tile storage (tile_size^2 words)
                   If None and allocator provided, will allocate automatically
        allocator: Optional MemoryAllocator for temp buffer allocation

    Note:
        Matrices must be stored in tile-major order.
    """
    from compiler.instructions import matmul, add
    
    t = tile_size
    t2 = t * t  # words per tile

    # Validate dimensions
    if M % t != 0 or N % t != 0 or K % t != 0:
        raise ValueError(f"Dimensions M={M}, N={N}, K={K} must be multiples of tile_size={t}")

    M_tiles, N_tiles, K_tiles = M // t, N // t, K // t

    # Handle temp buffer
    if temp_addr is None:
        if allocator is not None:
            temp_addr = allocator.alloc("_tiled_matmul_temp", t2)
        else:
            raise ValueError("Must provide temp_addr or allocator for tiled_matmul")

    # Triple nested loop over tiles
    for i in range(M_tiles):
        for j in range(N_tiles):
            Z_tile_addr = Z_addr + (i * N_tiles + j) * t2
            for k in range(K_tiles):
                # Input tile addresses
                X_tile_addr = X_addr + (i * K_tiles + k) * t2
                W_tile_addr = W_addr + (j * K_tiles + k) * t2

                if k == 0:
                    matmul(W_tile_addr, X_tile_addr, Z_tile_addr, m=t)
                else:
                    matmul(W_tile_addr, X_tile_addr, temp_addr, m=t)
                    for elem in range(t2):
                        add(Z_tile_addr + elem, temp_addr + elem, Z_tile_addr + elem)

    # Free temp buffer if we allocated it
    if allocator is not None:
        allocator.free("_tiled_matmul_temp")
