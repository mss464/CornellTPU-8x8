@kernel
def compehensive_kernel(ASimd: Param, BSimd: Param, AddOut: Param, ReluOut: Param, W4: Param, X4: Param, Z4: Param):
    from compiler.instructions import vload, vadd, vrelu, vstore
    # SIMD
    vload(0, ASimd)
    vload(1, BSimd)
    vadd(2, 0, 1)
    vstore(2, AddOut)
    vrelu(3, 0)
    vstore(3, ReluOut)

    # 4x4 MatMul
    from demos.kernels.matmul import matmul_4x4
    matmul_4x4(W=W4, X=X4, Z=Z4)
