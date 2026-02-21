Integrating TinyTorch with MiniTPU.

# MVP: 13_transformer

---

## 🕸️ Execution Analysis: NumPy Dependency Graph

Tracing the `13_transformer.py` forward pass revealed exactly which NumPy signatures underpin the Transformer architecture.

### 📊 Observed NumPy Calls
These functions are the "mathematical glue" between TinyTorch abstractions and raw CPU/TPU kernels.

| Function | Context | Callee Dependency (Internal) |
| :--- | :--- | :--- |
| `np.matmul` | Linear Layers, Attention Scores | `_validate_matmul_shapes`, `gemm` |
| `np.mean` | Layer Normalization | `np._mean` → `_count_reduce_items` |
| `np.max` | Softmax Stability | `np._wrapreduction` |
| `np.sum` | Softmax Denominator | `np._wrapreduction` |
| `np.reshape` | Attention Head Splitting | `np._reshape_dispatcher` → `np.prod` |
| `np.transpose` | Attention Memory Layout | `np._transpose_dispatcher` |
| `np.exp` | Softmax / GELU | Internal transcendental kernel |

### 🌳 Dependency Trace
Transitions happen from high-level `tinytorch` Tensor logic into NumPy's C-extension entry points:
- **TinyTorch Layer** (`attention.py`) ➔ Calls `np.matmul`
- **NumPy Entry** (`fromnumeric.py`) ➔ Dispatchers handle shape validation.
- **Compiled Kernel** (`multiarray_umath.so`) ➔ Final hardware-bound execution.

---

## 🚀 Requirement Analysis: Future TPU Operators

To port the full Transformer to a Mini TPU program (like [mlp.tu](file:///home/sk3463/main/projects/mini-tpu/workflow/programs/mlp.tu)), we must bridge the gap between current [ISA](file:///home/sk3463/main/projects/mini-tpu/compiler/instructions.py) and needed mathematics.

### 1. Reduction Engine (Sum/Mean)
- **Math**: $\sum_{i=1}^{D} x_i$ and $\frac{1}{D} \sum_{i=1}^{D} x_i$ (Normalization).
- **Observed Shapes**: `(1, 4, 32)` → reduction over `axis=-1` (dim 32).
- **Target Range**: $D \in \{64, 128, 256, 512, 768\}$ (Standard Embedding Sizes).

### 2. Transcendental Unit (Softmax/GELU)
- **Math**: $e^x$, $\tanh(x)$, and $\text{erf}(x)$.
- **Observed Shapes**: `(1, 4, 128)` for MLP activations; `(B, H, S, S)` for attention where $S \le 2048$.
- **Target Range**: Point-wise throughput for tens of thousands of FP32 elements per block.

### 3. Tiled DMA (Transpose/Reshape)
- **Math**: $X^T$ and Head Splitting.
- **Observed Shapes**: `(1, 4, 32)` → `(1, 4, 2, 16)` (Reshape) and `(1, 2, 4, 16)` (Transpose).
- **Target Range**: Multi-dimensional strided access for shapes up to $(S, S)$ where $S = 2048$.

### 4. Systolic MatMul (GEMM)
- **Math**: $Z = X @ W^T$
- **Observed Shapes**:
    - `(4, 32) @ (32, 32)` (Attention/Projection)
    - `(4, 32) @ (32, 128)` (Expansion)
    - `(4, 128) @ (128, 32)` (Contraction)
- **Target Range**: Tiled execution of $M \times K \times N$ where $K = \text{embed\_dim}$, $N = 4 \times K$.