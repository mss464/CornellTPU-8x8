from compiler import Program
from demos.kernels.vpu_simd import vector_add_simd, vector_mul_simd, fused_mlp_layer_simd

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

    for chunk in range(4):
        off = chunk * 8
        prog.call(vector_add_simd, A=vec_a_32+off, B=vec_b_32+off, C=add_out_32+off)
        prog.call(vector_mul_simd, A=vec_a_32+off, B=vec_b_32+off, C=mul_out_32+off)
        prog.call(fused_mlp_layer_simd, X=mlp_x+off, W=mlp_w+off, Bias=mlp_bias+off, Y=mlp_out+off)

    return prog
