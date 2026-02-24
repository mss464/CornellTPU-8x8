from compiler.compile import kernel, Param, Program
from compiler.instructions import matmul

@kernel
def gemm_4x4(W: Param, X: Param, Z: Param):
    """
    Systolic 4x4 matrix multiplication.
    Z = X @ W^T
    """
    matmul(W, X, Z, 4)

def define_program() -> Program:
    """
    Defines the static compilation boundary. 
    Allocates 16 words (4x4) per parameter to reserve memory maps.
    """
    prog = Program()
    addr_w = prog.alloc("W", 16)
    addr_x = prog.alloc("X", 16)
    addr_z = prog.alloc("Z", 16)
    
    prog.call(gemm_4x4, W=addr_w, X=addr_x, Z=addr_z)
    
    return prog
