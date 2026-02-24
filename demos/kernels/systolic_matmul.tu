from compiler.compile import kernel, Param, Program
from compiler.instructions import matmul, vload, vadd, vstore

@kernel
def matmul_32x32(W: Param, X: Param, Z: Param):
    """
    Primitive 32x32 matmul using the hardware systolic array.
    Computes Z = X @ W^T
    """
    # The m=32 parameter is captured during tracing and encoded as length=1024
    matmul(W, X, Z, m=32)

@kernel
def tiled_matmul_32x32(W: Param, X: Param, Z: Param, temp: Param, M: int, N: int, K: int):
    """
    Tiled Matrix Multiplication for 32x32 tiles.
    M, N, K are matrix dimensions (must be multiples of 32).
    """
    t = 32
    t2 = t * t
    
    M_tiles = M // t
    N_tiles = N // t
    K_tiles = K // t
    
    for i in range(M_tiles):
        for j in range(N_tiles):
            # Address of the output tile C[i, j]
            Z_tile = Z + (i * N_tiles + j) * t2
            
            for k in range(K_tiles):
                # Address of input tiles A[i, k] and B[j, k]
                # Note: Hardware matmul computes X @ W^T, so W is weights (B)
                X_tile = X + (i * K_tiles + k) * t2
                W_tile = W + (j * K_tiles + k) * t2
                
                if k == 0:
                    # First tile: direct MatMul
                    matmul(W_tile, X_tile, Z_tile, m=t)
                else:
                    # Subsequent tiles: MatMul to temp then accumulate
                    matmul(W_tile, X_tile, temp, m=t)
                    
                    # Accumulate 1024 elements (32x32) using 8-lane SIMD VPU
                    for offset in range(0, t2, 8):
                        vload(0, Z_tile + offset)
                        vload(1, temp + offset)
                        vadd(2, 0, 1)
                        vstore(2, Z_tile + offset)

def define_program() -> Program:
    """
    Standard static program definition.
    Benchmarks a 64x64x64 MatMul (2x2x2 tiles).
    """
    prog = Program()
    
    # Dimensions
    M, N, K = 64, 64, 64
    t = 32
    t2 = t * t
    
    # Allocate BRAM (Word-addressed)
    # A: 64x64 = 4096 words
    # B: 64x64 = 4096 words
    # C: 64x64 = 4096 words
    # temp: 32x32 = 1024 words
    W_addr = prog.alloc("W", N * K)
    X_addr = prog.alloc("X", M * K)
    Z_addr = prog.alloc("Z", M * N)
    temp_addr = prog.alloc("temp", t2)
    
    # Schedule the kernel call
    prog.call(tiled_matmul_32x32, W=W_addr, X=X_addr, Z=Z_addr, temp=temp_addr, M=M, N=N, K=K)
    
    return prog
