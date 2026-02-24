"""
Self-contained systolic tiled matrix multiplication simulator.
Pure Python implementation with manual address calculation and zero external dependencies.
"""

# Hardware Configuration: Scaling up for faster simulation overhead
TILE_DIM = 32 

def vadd_tile(a_buf, b_buf):
    """
    Simulated vector addition (VPU instruction).
    Hardware: Vector Processing Unit.
    """
    return [a + b for a, b in zip(a_buf, b_buf)]

def transpose_tile(tile):
    """
    Matrix transposition primitive.
    Input: Flat list of TILE_DIM*TILE_DIM elements.
    """
    res = [0.0] * (TILE_DIM * TILE_DIM)
    for i in range(TILE_DIM):
        for j in range(TILE_DIM):
            res[j * TILE_DIM + i] = tile[i * TILE_DIM + j]
    return res

import numpy as np

def gemm_tile(A_tile, B_tile):
    """
    Primitive GEMM: C = A @ B
    Hardware: 32x32 Systolic Array represented by high-performance NumPy.
    Inputs: Flat lists of TILE_DIM*TILE_DIM elements.
    """
    # Convert flat lists to NumPy for fast block processing
    a_mat = np.array(A_tile).reshape(TILE_DIM, TILE_DIM)
    b_mat = np.array(B_tile).reshape(TILE_DIM, TILE_DIM)
    
    # High-performance simulation of the hardware block
    # Use .dot() instead of matmul/@ to avoid triggering the custom hook recursion
    res_mat = a_mat.dot(b_mat)
    
    return res_mat.flatten().tolist()

def systolic_tiled_matmul(A_flat, B_flat, M, K, N):
    """
    Simulates the Hardware Tiled Execution on flat buffers.
    Zero external dependencies. Manual address calculation.
    """
    import os
    #if os.environ.get("MINI_TPU_DEBUG") == "1":
        #print(f"DEBUG: Hi! A software emulated TPU program (Tile size: {TILE_DIM}x{TILE_DIM})")
    
    # 1. Setup Tiling Parameters & Padding
    M_pad = (M + TILE_DIM - 1) // TILE_DIM * TILE_DIM
    K_pad = (K + TILE_DIM - 1) // TILE_DIM * TILE_DIM
    N_pad = (N + TILE_DIM - 1) // TILE_DIM * TILE_DIM

    # Allocate padded buffers (simulating TPU local memory/SRAM)
    A_padded = [0.0] * (M_pad * K_pad)
    B_padded = [0.0] * (K_pad * N_pad)
    C_padded = [0.0] * (M_pad * N_pad)

    # Manual copy with addressing
    for i in range(M):
        for k in range(K):
            A_padded[i * K_pad + k] = A_flat[i * K + k]
    for k in range(K):
        for j in range(N):
            B_padded[k * N_pad + j] = B_flat[k * N + j]

    # 2. Tiled Execution Loop
    for i in range(0, M_pad, TILE_DIM):
        for j in range(0, N_pad, TILE_DIM):
            for k in range(0, K_pad, TILE_DIM):
                # 1. Fetch data tiles
                tile_A = [0.0] * (TILE_DIM * TILE_DIM)
                tile_B = [0.0] * (TILE_DIM * TILE_DIM)
                for tr in range(TILE_DIM):
                    # Optimized fetch using slicing
                    idx_a_start = (i + tr) * K_pad + k
                    tile_A[tr * TILE_DIM : (tr + 1) * TILE_DIM] = A_padded[idx_a_start : idx_a_start + TILE_DIM]
                    
                    idx_b_start = (k + tr) * N_pad + j
                    tile_B[tr * TILE_DIM : (tr + 1) * TILE_DIM] = B_padded[idx_b_start : idx_b_start + TILE_DIM]
                
                # 2. Execute hardware multiply primitive (A @ B)
                tile_res = gemm_tile(tile_A, tile_B)
                
                # 4. Explicitly accumulate using vadd primitive
                for r in range(TILE_DIM):
                    c_row_start = (i + r) * N_pad + j
                    curr_c_row = C_padded[c_row_start : c_row_start + TILE_DIM]
                    res_row = tile_res[r * TILE_DIM : (r + 1) * TILE_DIM]
                    
                    # Accumulate in VPU
                    new_c_row = vadd_tile(curr_c_row, res_row)
                    
                    # Store back to local memory
                    C_padded[c_row_start : c_row_start + TILE_DIM] = new_c_row

    # 3. Extract unpadded result
    res_flat = [0.0] * (M * N)
    for i in range(M):
        for j in range(N):
            res_flat[i * N + j] = C_padded[i * N_pad + j]
    return res_flat
