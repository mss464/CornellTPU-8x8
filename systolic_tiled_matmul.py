"""
Self-contained systolic tiled matrix multiplication simulator.
Pure Python implementation with manual address calculation and zero external dependencies.
"""

def vadd4(a_buf, b_buf):
    """
    Simulated 4-element vector addition (VPU instruction).
    Hardware: Vector Processing Unit.
    """
    return [a_buf[i] + b_buf[i] for i in range(4)]

def transpose4x4(tile):
    """
    4x4 matrix transposition primitive.
    Input: Flat list of 16 elements.
    """
    res = [0.0] * 16
    for i in range(4):
        for j in range(4):
            # res[j, i] = tile[i, j]
            res[j * 4 + i] = tile[i * 4 + j]
    return res

def gemm4x4(A_tile, B_tile):
    """
    Primitive 4x4 GEMM: C = A @ B.T
    Hardware: Systolic Array performing dot product of rows.
    Inputs: Flat lists of 16 elements.
    """
    res = [0.0] * 16
    for i in range(4):
        for j in range(4):
            # Compute dot product of Row i of A and Row j of B
            dot = 0.0
            for k in range(4):
                # Manual address calculation for 4x4 tiles
                idx_a = i * 4 + k
                idx_b = j * 4 + k
                dot += A_tile[idx_a] * B_tile[idx_b]
            res[i * 4 + j] = dot
    return res

def systolic_tiled_matmul(A_flat, B_flat, M, K, N):
    """
    Simulates the Hardware Tiled Execution on flat buffers.
    Zero external dependencies. Manual address calculation.
    """
    # 1. Setup Tiling Parameters & Padding
    M_pad = (M + 3) // 4 * 4
    K_pad = (K + 3) // 4 * 4
    N_pad = (N + 3) // 4 * 4

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

    # 2. Tiled Execution Loop (Strictly loops, address calculation, and primitives)
    for i in range(0, M_pad, 4):
        for j in range(0, N_pad, 4):
            for k in range(0, K_pad, 4):
                # 1. Fetch data tiles (A_block and B_block)
                tile_A = [0.0] * 16
                tile_B = [0.0] * 16
                for tr in range(4):
                    for tc in range(4):
                        # A_tile[row, col] = A_padded[i + row, k + col]
                        tile_A[tr * 4 + tc] = A_padded[(i + tr) * K_pad + (k + tc)]
                        # B_tile[row, col] = B_padded[k + row, j + col]
                        tile_B[tr * 4 + tc] = B_padded[(k + tr) * N_pad + (j + tc)]
                
                # 2. Simulate hardware data preparation: Explicit Transpose on B tile
                # Since gemm4x4 performs A@B^T, we transpose B_block to get A@B.
                t_tile_B = transpose4x4(tile_B)
                
                # 3. Execute hardware multiply primitive (A @ B^T)
                tile_res = gemm4x4(tile_A, t_tile_B)
                
                # 4. Explicitly accumulate using vadd4 primitive (VPU/Accumulator)
                # Row-by-row on the 4-element vectors
                for r in range(4):
                    c_row_start = (i + r) * N_pad + j
                    # Simulate vector load from local memory
                    curr_c_row = [C_padded[c_row_start + c] for c in range(4)]
                    res_row = [tile_res[r * 4 + c] for c in range(4)]
                    
                    # Accumulate in VPU
                    new_c_row = vadd4(curr_c_row, res_row)
                    
                    # Store back to local memory
                    for c in range(4):
                         C_padded[c_row_start + c] = new_c_row[c]

    # 3. Extract unpadded result (simulating DMA out)
    res_flat = [0.0] * (M * N)
    for i in range(M):
        for j in range(N):
            res_flat[i * N + j] = C_padded[i * N_pad + j]
    return res_flat
