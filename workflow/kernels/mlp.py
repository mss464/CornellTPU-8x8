"""
MLP Model Definition for Mini-TPU.

This module provides a build() function that traces a full 
MLP forward and backward pass.
"""

import numpy as np
from compiler.compile import kernel, Param
from compiler.instructions import matmul, add, sub, mul, relu, relu_derivative, get_instruction_log, mem

m = 4

def weight_mul(W, X, m=4):
    W = np.array(W, dtype=np.float32)
    X = np.array(X, dtype=np.float32)
    return np.matmul(X, W.T).astype(np.float32)

def bias_add(z, b):
    z = np.array(z, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    if b.ndim == 2 and b.shape[1] == 1: b = b.flatten()
    if z.ndim == 2 and z.shape[0] == 1: z = z.flatten() 
    return np.add(z, b).astype(np.float32)

def relu_op(z):
    return np.maximum(0.0, z).astype(np.float32)

def forward_pass(W, X, b, X_addr, W_addr, Z_addr, b_addr, Y_addr, ZERO_addr, A_addr, m=4):
    Y = weight_mul(W,X)
    matmul(W_addr, X_addr, Z_addr)
    A = np.zeros_like(Y)
    for i in range(len(Y)):
      Y[i] = bias_add(Y[i], b)
      A[i] = relu_op(Y[i])
    for i in range(m):
      for j in range(m):
        add(Z_addr + (i*m + j), b_addr+j, Y_addr + (i*m + j))
        relu(Y_addr + (i*m + j), ZERO_addr,  A_addr + (i*m + j))
    return Y.astype(np.float32), A.astype(np.float32)

def loss(Y, Y_prime, Y_addr, Y_prime_addr, diff_addr, squared_addr, sum_addr, const_addr_0625, loss_addr, const_addr_0125, dA_addr, m=4):
    diff = Y - Y_prime
    squared = np.square(diff)
    for i in range(m * m):
      sub(Y_addr + i, Y_prime_addr + i, diff_addr + i)
      mul(diff_addr+i, diff_addr+i, squared_addr+i)
    l = np.sum(squared)
    for i in range(m*m):
      add(sum_addr, squared_addr+i, sum_addr)
    mul(sum_addr, const_addr_0625, loss_addr)
    dA = np.float32(0.125) * diff
    for i in range(m*m):
      mul(diff_addr + i, const_addr_0125, dA_addr + i)
    return np.float32(0.0625 * l), dA.astype(np.float32)

def backward_pass(W, X, b, Y, dA, Y_addr, ZERO_addr, relu_deriv_addr, dA_addr, dZ_addr, X_addr, dW_addr,const_addr_025, db_addr, W_addr, W_addr_transposed, dX_addr, m=4):
    dZ = np.zeros_like(dA)
    for i in range(len(dA)):
      dZ[i] = dA[i] * (Y[i] > 0).astype(np.float32)
    for i in range(m * m):
      relu_derivative(Y_addr + i, ZERO_addr , relu_deriv_addr + i)
      mul( dA_addr + i, relu_deriv_addr + i, dZ_addr + i)
    matmul(X_addr, dZ_addr, dW_addr)
    for i in range(m):
      for k in range(m):
          add(dZ_addr + i*m + k, db_addr + i, db_addr + i)
    for i in range(m):
      mul(db_addr + i, const_addr_025, db_addr + i)
    for i in range(m):
      for j in range(m):
          add(W_addr + j*m + i, ZERO_addr, W_addr_transposed + i*m + j)
    matmul(W_addr_transposed, dZ_addr, dX_addr)
    return (dZ @ X.T), (0.25 * np.sum(dZ, axis=1, keepdims=True)), (dZ @ W)

def build(): 
    """Tracing entry point for compiler CLI."""
    mem.reset()
    ZERO_addr = mem.alloc("zero", 1)
    X_addr = mem.alloc("X", 16)
    W_addr = mem.alloc("W", 16)
    Z_addr = mem.alloc("Z", 16)
    W_addr_transposed = mem.alloc("W.T", 16)
    b_addr = mem.alloc("b", 4)
    Y_addr = mem.alloc("Y", 16)
    A_addr = mem.alloc("A", 16)
    Y_prime_addr = mem.alloc("Y_prime", 16)
    dA_addr = mem.alloc("dA", 16)
    dZ_addr = mem.alloc("dZ", 16)
    dW_addr = mem.alloc("dW", 16)
    db_addr = mem.alloc("db", 4)
    dX_addr = mem.alloc("dX", 16)
    diff_addr = mem.alloc("diff", 16)
    squared_addr = mem.alloc("sqaured", 16)
    sum_addr = mem.alloc("sum", 16)
    loss_addr = mem.alloc("loss", 1)
    relu_deriv_addr = mem.alloc("relu_deriv", 16)
    c0625 = mem.alloc("c0625", 1)
    c125 = mem.alloc("c125", 1)
    c025 = mem.alloc("c025", 1)

    W = np.random.randn(4, 4).astype(np.float32)  
    X = np.random.randn(4, 4).astype(np.float32)  
    b = np.random.randn(4, 1).astype(np.float32) 
    Y_prime = np.random.randn(4, 4).astype(np.float32)

    Y, A = forward_pass(W, X, b, X_addr, W_addr, Z_addr, b_addr, Y_addr, ZERO_addr, A_addr)
    _, dA = loss(Y, Y_prime, Y_addr, Y_prime_addr, diff_addr, squared_addr, sum_addr, c0625, loss_addr, c125, dA_addr)
    backward_pass(W, X, b, Y, dA, Y_addr, ZERO_addr, relu_deriv_addr, dA_addr, dZ_addr, X_addr, dW_addr, c025, db_addr, W_addr, W_addr_transposed, dX_addr)
    print("Success: MLP Trace Generated.")
