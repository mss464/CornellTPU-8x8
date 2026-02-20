from compiler.compile import kernel, Param, Program
from compiler.instructions import vadd, vload, vstore

@kernel
def dummy_add(A: Param, B: Param, C: Param):
    """
    Very simple vector add kernel to verify board execution.
    """
    vload(0, A)
    vload(1, B)
    vadd(2, 0, 1)
    vstore(2, C)

def define_program() -> Program:
    prog = Program()
    # Allocate small 8-word buffers
    addr_a = prog.alloc("A", 8)
    addr_b = prog.alloc("B", 8)
    addr_c = prog.alloc("C", 8)
    
    prog.call(dummy_add, A=addr_a, B=addr_b, C=addr_c)
    return prog
