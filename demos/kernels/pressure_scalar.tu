from compiler import Program, kernel, Param

# Scalar kernels (one element per instruction)
@kernel
def scalar_add_32(A: Param, B: Param, C: Param):
    from compiler.instructions import add
    for i in range(32): add(A + i, B + i, C + i)

@kernel
def scalar_mul_32(A: Param, B: Param, C: Param):
    from compiler.instructions import mul
    for i in range(32): mul(A + i, B + i, C + i)

@kernel
def scalar_mlp_32(X: Param, W: Param, Bias: Param, Zero: Param, Y: Param):
    from compiler.instructions import mul, add, relu
    for i in range(32): mul(X + i, W + i, Y + i)
    for i in range(32): add(Y + i, Bias + i, Y + i)
    for i in range(32): relu(Y + i, Zero, Y + i)

def define_program():
    prog = Program()
    
    vec_a_32 = prog.alloc("vec_a_32", 32)
    vec_b_32 = prog.alloc("vec_b_32", 32)
    add_out_32 = prog.alloc("add_out_32", 32)
    mul_out_32 = prog.alloc("mul_out_32", 32)
    mlp_x = prog.alloc("mlp_x", 32)
    mlp_w = prog.alloc("mlp_w", 32)
    mlp_bias = prog.alloc("mlp_bias", 32)
    mlp_out = prog.alloc("mlp_out", 32)
    zero = prog.alloc("zero", 1)

    prog.call(scalar_add_32, A=vec_a_32, B=vec_b_32, C=add_out_32)
    prog.call(scalar_mul_32, A=vec_a_32, B=vec_b_32, C=mul_out_32)
    prog.call(scalar_mlp_32, X=mlp_x, W=mlp_w, Bias=mlp_bias, Zero=zero, Y=mlp_out)

    return prog
