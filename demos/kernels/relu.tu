from compiler.compile import kernel, Param, Program
from compiler.instructions import vload, vrelu, vstore

@kernel
def relu_16(X: Param, Y: Param):
    """
    Vectorized ReLU over 16 elements.
    """
    vload(0, X)
    vrelu(1, 0)
    vstore(1, Y)
    
    # 2nd chunk of 8
    vload(2, X + 8)
    vrelu(3, 2)
    vstore(3, Y + 8)

def define_program() -> Program:
    """
    Defines the static compilation boundary.
    Allocates 16 words per vector.
    """
    prog = Program()
    addr_x = prog.alloc("X", 16)
    addr_y = prog.alloc("Y", 16)
    
    prog.call(relu_16, X=addr_x, Y=addr_y)
    
    return prog
