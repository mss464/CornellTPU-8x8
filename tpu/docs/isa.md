# ISA

NOTE: This document is a design contract between the RTL and software subteams.
Any change to encoding or semantics must be coordinated and updated here.

## Scope
This document defines the CornellTPU 64-bit instruction encoding and execution
semantics. It is the single source of truth for instruction layout, mode
values, and per-op behavior.

# ISA Change Workflow

## Impact Analysis: When ISA Changes

When the Instruction Set Architecture (ISA) changes, multiple components need to be updated. This document outlines the complete workflow.

## Components Affected by ISA Changes

### 1. Hardware (RTL) ✅ Covered by Current Flow
**Location:** `tpu/tensorcore/`

**What Changes:**
- `decoder.sv` - Instruction decode logic
- ISA documentation in comments/headers

**Current Build Flow:**
```bash
make -C tpu bitstream TARGET=ultra96-v2
```
✅ **Auto-handled** - RTL changes are automatically picked up by synthesis

**Verification:**
- Rebuild bitstream (captures new decoder)
- Run board tests

---

### 2. Compiler/Assembler ⚠️ NOT Fully Covered
**Location:** `compiler/`

**What Changes:**
- `compiler/assembler.py` - Instruction encoding
- `compiler/kernels/` - Kernel implementations using new instructions
- `compiler/tpu_txt.py` - TPU assembly syntax

**Current Flow Gaps:**
- ❌ No automated check that compiler matches RTL ISA
- ❌ No ISA version tracking
- ❌ Compiler tests not integrated into board-test flow

**What Should Change:**
1. **Add ISA version constant** in both RTL and compiler
2. **Version check** during bitstream programming
3. **Compiler unit tests** for instruction encoding

---

### 3. Test Programs ⚠️ Partially Covered
**Location:** `tests/ultra96-v2/programs/`

**What Changes:**
- Program definitions if they use new instructions
- Memory layouts if ISA changes data formats

**Current Flow:**
```bash
python tests/ultra96-v2/programs/comprehensive.py  # Recompile
make board-comprehensive                            # Test
```

✅ **Partially handled** - Programs are recompiled, but no validation that they match ISA

**What Should Change:**
1. **ISA-aware program generator** - annotate which ISA version each program targets
2. **Compiler warning** if using deprecated instructions

---

### 4. Documentation ❌ NOT Covered
**Location:** `docs/`

**What Changes:**
- ISA specification (currently no formal spec!)
- Instruction encoding tables
- Example programs

**Current Flow:**
- ❌ No automation - manual updates required

**What Should Change:**
1. **Create formal ISA spec** (`docs/isa.md`)
2. **Auto-generate** instruction tables from decoder RTL
3. **Versioned ISA docs** in git

---

## Recommended Changes for ISA Evolution

### Phase 1: Version Tracking (High Priority)

**1. Add ISA Version to RTL**
```systemverilog
// tpu/tensorcore/decoder.sv
localparam ISA_VERSION = 8'h01;  // v0.1
```

**2. Add ISA Version to Compiler**
```python
# compiler/assembler.py
ISA_VERSION = "0.1"
ISA_MAGIC = 0x54505501  # "TPU" + version 0x01
```

**3. Bitstream Metadata**
- Embed ISA version in bitstream metadata
- Driver checks version on init:
```python
def __init__(self, bitstream):
    self.isa_version = read_isa_version_from_bitstream()
    if self.isa_version != COMPILER_ISA_VERSION:
        raise IncompatibleISAError(...)
```

### Phase 2: Formal ISA Specification (Medium Priority)

**1. Create `docs/isa.md`**
```markdown
# Mini-TPU ISA v0.1

## Instruction Format
[63:58] opcode
[57:52] dest
[51:46] src1
[45:40] src2
...

## Instruction Set
| Opcode | Mnemonic | Operation | Format |
|--------|----------|-----------|--------|
| 0x00   | NOP      | No operation | - |
| 0x01   | VADD     | Vec add   | R-type |
...
```

**2. Auto-Generate from RTL**
```bash
# Extract opcodes from decoder.sv
scripts/extract_isa_from_rtl.py tpu/tensorcore/decoder.sv > docs/isa_generated.md
```

### Phase 3: Compiler-RTL Consistency Checks (High Priority)

**1. Add Compiler Tests**
```python
# tests/test_compiler/test_isa_consistency.py
def test_opcode_matches_rtl():
    """Verify compiler opcodes match RTL decoder."""
    rtl_opcodes = extract_opcodes_from_rtl("tpu/tensorcore/decoder.sv")
    compiler_opcodes = assembler.OPCODE_MAP
    assert rtl_opcodes == compiler_opcodes
```

**2. Add to CI/Board Test Flow**
```bash
# Before board tests
make test-isa-consistency  # Fails if compiler/RTL mismatch
```

### Phase 4: Backward Compatibility Strategy (Low Priority)

For production systems supporting multiple ISA versions:

**1. Multi-Version Compiler**
```python
class Assembler:
    def __init__(self, target_isa="latest"):
        self.isa = load_isa_version(target_isa)
```

**2. Bitstream ISA Reporting**
```python
tpu = TpuDriver(bitstream)
print(f"TPU ISA: {tpu.isa_version}")
```

**3. Feature Detection**
```python
if tpu.supports_instruction("VDIV"):
    prog.emit("VDIV", ...)
else:
    prog.emit_division_workaround(...)
```

---

## Updated Build & Test Flow for ISA Changes

### Current Flow (Partial Coverage)
```bash
# 1. Modify RTL decoder
vim tpu/tensorcore/decoder.sv

# 2. Modify compiler (manual sync)
vim compiler/assembler.py

# 3. Rebuild bitstream
make -C tpu bitstream TARGET=ultra96-v2

# 4. Test (no ISA validation!)
make -C tests board-comprehensive BIT=... HWH=...
```

### Recommended Flow (Full Coverage)
```bash
# 1. Update ISA version constant
vim tpu/tensorcore/decoder.sv        # ISA_VERSION++
vim compiler/assembler.py             # ISA_VERSION++

# 2. Modify decoder RTL
vim tpu/tensorcore/decoder.sv

# 3. Modify compiler to match
vim compiler/assembler.py

# 4. Verify consistency (NEW)
make test-isa-consistency  # Fails if mismatch

# 5. Update formal spec (NEW)
scripts/generate_isa_docs.py

# 6. Rebuild bitstream
make -C tpu bitstream TARGET=ultra96-v2

# 7. Run compiler unit tests (NEW)
pytest tests/test_compiler/

# 8. Recompile test programs
python tests/ultra96-v2/programs/*.py

# 9. Board test with version check
make -C tests board-comprehensive BIT=... HWH=...
# (Driver auto-checks ISA version match)
```

---

## Implementation Checklist

**Immediate (Can Implement Now):**
- [ ] Add ISA version constants to RTL and compiler
- [ ] Create `docs/isa.md` with current instruction set
- [ ] Add compiler unit tests (`tests/test_compiler/`)
- [ ] Document ISA change workflow (this file)

**Short-term (Next Sprint):**
- [ ] Add ISA version check to TpuDriver init
- [ ] Create ISA consistency test
- [ ] Add "ISA-Version" field to bitstream metadata/HWH
- [ ] Integrate compiler tests into board-test flow

**Long-term (Future):**
- [ ] Auto-generate ISA docs from RTL
- [ ] Multi-version compiler support
- [ ] Feature detection API
- [ ] ISA versioning in CI

---

## Example: Adding a New Instruction

**Scenario:** Add `VMAX` (vector maximum) instruction

**Step-by-Step:**

1. **Update ISA Version**
   ```systemverilog
   // decoder.sv
   localparam ISA_VERSION = 8'h02;  // v0.1 -> v0.2
   ```

2. **Add to RTL Decoder**
   ```systemverilog
   // decoder.sv
   localparam OPCODE_VMAX = 6'b010101;

   case (opcode)
       OPCODE_VMAX: begin
           unit_sel = UNIT_VPU;
           vpu_op = VPU_OP_MAX;
       end
   ```

3. **Add to VPU**
   ```systemverilog
   // vpu_op.sv
   localparam VPU_OP_MAX = 3'd5;

   case (op)
       VPU_OP_MAX: result = (a > b) ? a : b;
   ```

4. **Update Compiler**
   ```python
   # assembler.py
   ISA_VERSION = "0.2"

   OPCODE_MAP = {
       "VMAX": 0b010101,
       ...
   }
   ```

5. **Add Kernel**
   ```python
   # compiler/kernels/vpu.py
   def vmax(prog, src_a, src_b, dest):
       prog.emit("VMAX", dest=dest, src1=src_a, src2=src_b)
   ```

6. **Add Test**
   ```python
   # tests/test_compiler/test_vmax.py
   def test_vmax_encoding():
       prog = Program()
       prog.emit("VMAX", dest=0, src1=1, src2=2)
       assert prog.instructions[0] & 0xFC == (0b010101 << 58)
   ```

7. **Rebuild & Test**
   ```bash
   make test-isa-consistency  # Verify sync
   make -C tpu bitstream TARGET=ultra96-v2
   pytest tests/test_compiler/
   make -C tests board-comprehensive BIT=... HWH=...
   ```

---

## Conclusion

**Current State:**
- ✅ Hardware changes flow through rebuild automatically
- ⚠️ Compiler changes have no validation against RTL
- ❌ No ISA versioning or compatibility checks

**Recommended Additions:**
1. ISA version tracking (RTL + compiler)
2. Formal ISA specification
3. Compiler-RTL consistency tests
4. Runtime version checking

**Impact on Build Flow:**
- Add pre-build ISA consistency check
- Add compiler unit tests to validation
- Add ISA version to bitstream metadata

With these changes, ISA evolution becomes **safe and traceable**.


## Instruction Word Overview
- Fixed-width 64-bit instructions stored in IRAM and executed sequentially.
- Bit numbering uses [63] as MSB and [0] as LSB.
- Common address fields (all modes):
  - ADDR_A  [61:49]
  - ADDR_B  [48:36]
  - ADDR_OUT [35:23]
- Lower bits are mode-specific:
  - VPU: ADDR_CONST [22:10], OPCODE [9:0]
  - Systolic/Vadd: LEN [22:0]

## Mode Field
MODE is encoded in bits [63:62].

| MODE | Meaning              |
|-----:|----------------------|
|   0  | VPU instruction      |
|   1  | Systolic instruction |
|   2  | TMA instruction      |
|   3  | Halt                 |

Invalid mode values are undefined.

## Addressing and Data Model
- All ADDR_* fields are 13-bit word addresses into BRAM (0..8191).
- Each BRAM word is 32 bits (fp32 in the current system).
- ADDR_CONST points at a BRAM word containing a constant (commonly zero).
- IRAM holds up to 256 instructions. Programs must end with HALT.

## Instruction Formats

### VPU (MODE = 0)

The VPU supports both legacy scalar operations and modern SIMD vector operations
through a VPU_TYPE field.

**Common VPU Fields:**

| Field      | Bits    | Description                          |
|------------|---------|--------------------------------------|
| MODE       | [63:62] | Must be 0                            |
| ADDR_A     | [61:49] | Base address of input/load vector    |
| ADDR_B     | [48:36] | Base address of input vector B       |
| ADDR_OUT   | [35:23] | Base address of output/store vector  |
| VPU_TYPE   | [22:20] | VPU instruction class (3 bits)       |
| (variable) | [19:0]  | Type-specific fields                 |

**VPU_TYPE Values:**

| VPU_TYPE | Class      | Description                              |
|---------:|------------|------------------------------------------|
|        0 | SCALAR     | Legacy element-wise operations           |
|        1 | VLOAD      | Load 8 FP32 values to vector register    |
|        2 | VSTORE     | Store 8 FP32 values from vector register |
|        3 | VCOMPUTE   | SIMD vector operations (8 lanes)         |
|      4-7 | RESERVED   | Future extension                         |

---

#### VPU Type 0: SCALAR (Legacy)

**Format:**

| Field      | Bits    | Description                          |
|------------|---------|--------------------------------------|
| MODE       | [63:62] | 0                                    |
| ADDR_A     | [61:49] | Base address of input vector A       |
| ADDR_B     | [48:36] | Base address of input vector B       |
| ADDR_OUT   | [35:23] | Base address of output vector        |
| VPU_TYPE   | [22:20] | 0                                    |
| ADDR_CONST | [19:7]  | Base address of constant element     |
| OPCODE     | [6:0]   | VPU operation selector               |

**Semantics:** Operates on a single element per instruction. To process longer
vectors, software must issue multiple instructions.

**Opcodes:**

| Opcode | Mnemonic        | Operation                   |
|------:|-----------------|-----------------------------|
|     0 | ADD             | Element-wise addition       |
|     1 | SUB             | Element-wise subtraction    |
|     2 | RELU            | Rectified Linear Unit       |
|     3 | MUL             | Element-wise multiplication |
|     4 | RELU_DERIVATIVE | ReLU derivative             |

**ADDR_CONST usage:**
- RELU and RELU_DERIVATIVE use ADDR_CONST (typically pointing at a zero value).
- ADD, SUB, and MUL ignore ADDR_CONST; set it to 0.

---

#### VPU Type 1: VLOAD

Load 8 consecutive FP32 values from BRAM into a vector register.

**Format:**

| Field      | Bits    | Description                          |
|------------|---------|--------------------------------------|
| MODE       | [63:62] | 0                                    |
| ADDR_A     | [61:49] | BRAM start address                   |
| ADDR_B     | [48:36] | 0 (reserved)                         |
| ADDR_OUT   | [35:23] | 0 (reserved)                         |
| VPU_TYPE   | [22:20] | 1                                    |
| RESERVED   | [19:17] | 0                                    |
| VREG_DST   | [16:14] | Destination vector register (0-7)    |
| RESERVED   | [13:0]  | 0                                    |

**Semantics:** `VREG_DST[0:7] = BRAM[ADDR_A + 0:7]`

**Example:**
```
vload v0, 0x100   # Load BRAM[0x100:0x107] → V0[0:7]
```

**Timing:** ~10-15 cycles (8 sequential BRAM reads with latency)

---

#### VPU Type 2: VSTORE

Store 8 FP32 values from a vector register to BRAM.

**Format:**

| Field      | Bits    | Description                          |
|------------|---------|--------------------------------------|
| MODE       | [63:62] | 0                                    |
| ADDR_OUT   | [61:49] | BRAM destination address             |
| ADDR_B     | [48:36] | 0 (reserved)                         |
| ADDR_A     | [35:23] | 0 (reserved)                         |
| VPU_TYPE   | [22:20] | 2                                    |
| RESERVED   | [19:17] | 0                                    |
| VREG_SRC   | [16:14] | Source vector register (0-7)         |
| RESERVED   | [13:0]  | 0                                    |

**Semantics:** `BRAM[ADDR_OUT + 0:7] = VREG_SRC[0:7]`

**Example:**
```
vstore v2, 0x200  # Store V2[0:7] → BRAM[0x200:0x207]
```

**Timing:** ~10-15 cycles (8 sequential BRAM writes)

---

#### VPU Type 3: VCOMPUTE

SIMD arithmetic operations on vector registers (8-lane parallel execution).

**Format:**

| Field      | Bits    | Description                          |
|------------|---------|--------------------------------------|
| MODE       | [63:62] | 0                                    |
| RESERVED   | [61:23] | 0                                    |
| VPU_TYPE   | [22:20] | 3                                    |
| VREG_DST   | [19:17] | Destination register (0-7)           |
| VREG_A     | [16:14] | Source register A (0-7)              |
| VREG_B     | [13:11] | Source register B (0-7)              |
| RESERVED   | [10:7]  | 0                                    |
| OPCODE     | [6:4]   | Vector operation (3 bits)            |
| SCALAR_B   | [3]     | 1 = broadcast VREG_B[0] to all lanes |
| RESERVED   | [2:0]   | 0                                    |

**Semantics (vector-vector, SCALAR_B=0):**
```
for i in 0..7:
    VREG_DST[i] = OP(VREG_A[i], VREG_B[i])
```

**Semantics (vector-scalar, SCALAR_B=1):**
```
scalar = VREG_B[0]  # Broadcast element 0
for i in 0..7:
    VREG_DST[i] = OP(VREG_A[i], scalar)
```

**OPCODE Values:**

| OPCODE | Mnemonic | Operation                |
|-------:|----------|--------------------------|
|      0 | VADD     | result = a + b           |
|      1 | VSUB     | result = a - b           |
|      2 | VMUL     | result = a * b           |
|      3 | VRELU    | result = max(a, 0)       |
|      4 | VMAX     | result = max(a, b)       |
|      5 | VMIN     | result = min(a, b)       |
|    6-7 | RESERVED | -                        |

**Examples:**
```
vadd v2, v0, v1       # V2[i] = V0[i] + V1[i] for i=0..7
vmul v3, v1, v0.s     # V3[i] = V1[i] * V0[0] (scalar broadcast)
vrelu v1, v1          # V1[i] = max(V1[i], 0) (in-place ReLU)
```

**Timing:** 1 cycle (true parallel execution)

---

#### Vector Register File

The SIMD VPU includes 8 vector registers (V0-V7), each holding 8 FP32 elements.

**Register File Specifications:**
- Number of registers: 8 (V0-V7)
- Elements per register: 8
- Element width: 32 bits (FP32)
- Total size per register: 256 bits
- Total register file size: 2048 bits (256 bytes)

**Access Properties:**
- Dual-port read (for binary operations like VADD)
- Single-port write
- Asynchronous read, synchronous write
- Reset initializes all registers to zero

**Usage Pattern:**
1. VLOAD: Load BRAM data into vector registers
2. VCOMPUTE: Perform SIMD operations on registers
3. VSTORE: Write results back to BRAM

---

#### SIMD VPU Example Programs

**Example 1: Vector Addition**
```
vload v0, 0x100        # V0 = A[0:7]
vload v1, 0x200        # V1 = B[0:7]
vadd v2, v0, v1        # V2 = V0 + V1
vstore v2, 0x300       # C[0:7] = V2
```
**Performance:** 4 instructions, ~25 cycles total (vs. 8 scalar VPU instructions @ 64 cycles)

**Example 2: Vector Scaling (Scalar Broadcast)**
```
vload v0, 0x100        # V0 = input[0:7]
vload v1, 0x200        # V1 = [scale, _, _, ...]
vmul v2, v0, v1.s      # V2 = V0 * V1[0] (broadcast)
vstore v2, 0x300       # output[0:7] = V2
```

**Example 3: Fused Multiply-Add (FMA pattern)**
```
vload v0, 0x100        # V0 = x[0:7]
vload v1, 0x200        # V1 = w[0:7]
vmul v2, v0, v1        # V2 = x * w
vload v3, 0x300        # V3 = bias[0:7]
vadd v2, v2, v3        # V2 = x*w + bias
vrelu v2, v2           # V2 = ReLU(x*w + bias)
vstore v2, 0x400       # Store result
```
**Performance:** 7 instructions, ~40 cycles (vs. 24 scalar VPU @ 192 cycles)

**Example 4: In-Place ReLU Activation**
```
vload v0, 0x100        # V0 = activations[0:7]
vrelu v0, v0           # V0 = max(V0, 0) (in-place)
vstore v0, 0x100       # Write back in-place
```

---

#### Performance Comparison: Scalar vs. SIMD VPU

| Operation | Scalar VPU | SIMD VPU (8-lane) | Speedup |
|-----------|------------|-------------------|---------|
| 8-element ADD | 8 instr × 8 cycles = 64 | 1 VADD (~1 cycle) + LOAD/STORE (~25 total) | ~2.5x |
| 16-element MUL | 16 × 8 = 128 cycles | 2 VMUL + LOAD/STORE (~50 total) | ~2.5x |
| Dot product (16) | 16 MUL + 15 ADD = 248 | 2 VMUL + 2 VADD + LOAD/STORE (~55 total) | ~4.5x |

**Note:** Actual speedup depends on LOAD/STORE overhead. For compute-heavy workloads
with register reuse, SIMD VPU approaches 8x speedup for pure compute operations.

### Systolic (MODE = 1)

| Field    | Bits    | Description                               |
|----------|---------|-------------------------------------------|
| MODE     | [63:62] | Must be 1                                 |
| ADDR_A   | [61:49] | Base address of weight matrix W           |
| ADDR_B   | [48:36] | Base address of input matrix X            |
| ADDR_OUT | [35:23] | Base address of output matrix Z           |
| LEN      | [22:0]  | Number of words to process (see note)     |

**Semantics**

The systolic array computes: `Z = X @ W^T` (input times weight-transposed).

Given `matmul W, X, Z`:
- W is stored row-major at ADDR_A (4x4 = 16 words)
- X is stored row-major at ADDR_B (4x4 = 16 words)
- Result Z = X @ W^T is written row-major to ADDR_OUT

This transposed-weight convention matches common neural network usage where
weights are stored in `[out_features, in_features]` layout.

**Notes**
- The current systolic array performs 4x4 matrix multiplication.
- LEN is encoded but currently ignored by hardware. Set LEN = 16 by convention.
- For larger matrices, use software tiling with VPU accumulation (see below).

### TMA (MODE = 2)

TMA (Tensor Memory Access) transfers a contiguous block of words between device memory and L2 SRAM. Initiated by the tensorcore during COMPUTE mode and handled by `tma_engine.sv` inside the L2 tile.

| Field     | Bits    | Description                                   |
|-----------|---------|-----------------------------------------------|
| MODE      | [63:62] | Must be 2                                     |
| DIR       | [61]    | 0 = DevMem → L2, 1 = L2 → DevMem             |
| DM_BASE   | [60:45] | Device memory base address (16-bit word addr) |
| L2_BASE   | [44:30] | L2 SRAM base address (15-bit word addr)       |
| LEN       | [29:14] | Transfer length in words (16-bit)             |
| RESERVED  | [13:0]  | Must be zero                                  |

**Semantics (DIR=0, DevMem → L2):**
```
L2[L2_BASE : L2_BASE+LEN-1] = DevMem[DM_BASE : DM_BASE+LEN-1]
```

**Semantics (DIR=1, L2 → DevMem):**
```
DevMem[DM_BASE : DM_BASE+LEN-1] = L2[L2_BASE : L2_BASE+LEN-1]
```

**Completion:** Hardware asserts `tma_done` (1-cycle pulse) when the transfer finishes. The tensorcore waits in `WAIT_TMA` state until this signal fires before fetching the next instruction.

**Constraints:** LEN must be ≤ 32768 (L2 size). DM_BASE + LEN must not exceed 65536 (DevMem size).

**Example:**
```
# Load 64 floats from DevMem[0x100] into L2[0x200]
tma dir=0 dm_base=0x100 l2_base=0x200 len=64
```

**Assembler mnemonic:** `tma <dir> <dm_base> <l2_base> <len>`

### Halt (MODE = 3)

HALT marks the end of the instruction stream. All bits other than MODE must be
zero. On HALT, the TPU transitions to IDLE.

## Execution Model
- Instructions are fetched from IRAM and executed in program order.
- No branching or predication; each instruction completes before the next.
- All programs must terminate with a HALT instruction.
- Unused fields must be zero. Invalid MODE or OPCODE values are undefined.

## Encoding Constraints
- MODE is 2 bits.
- ADDR_* fields are 13 bits (0..8191).
- LEN is 23 bits (0..8,388,607) but must not cause BRAM overrun.
- OPCODE is 10 bits; only values 0..4 are currently defined.

## Assembler Mnemonics (Software)
The current assembler uses these mnemonics:
- Systolic: `matmul <addr_w> <addr_x> <addr_out>`
- VPU Scalar: `add`, `sub`, `relu`, `mul`, `relu_derivative`
- VPU SIMD:
  - `vload <vreg> <addr>` - Load BRAM to vector register
  - `vstore <vreg> <addr>` - Store vector register to BRAM
  - `vadd <vdst> <va> <vb> [.s]` - Vector addition (.s = scalar broadcast)
  - `vsub <vdst> <va> <vb> [.s]` - Vector subtraction
  - `vmul <vdst> <va> <vb> [.s]` - Vector multiplication
  - `vrelu <vdst> <vsrc>` - Vector ReLU
  - `vmax <vdst> <va> <vb>` - Vector maximum
  - `vmin <vdst> <va> <vb>` - Vector minimum
- Control: `halt`
  - `tma <dir> <dm_base> <l2_base> <len>` - TMA block transfer (dir=0: devmem→L2, dir=1: L2→devmem)
- Pseudo: `load <addr> <len> <values>`, `store <addr> <len> <label>`

## Tiled Matrix Multiplication

For matrices larger than 4x4, software tiling decomposes the computation into
multiple 4x4 matmuls with VPU accumulation.

**Algorithm for MxN = MxK @ KxN (tile size t=4):**
```
for i in range(M // t):
    for j in range(N // t):
        for k in range(K // t):
            if k == 0:
                Z[i,j] = X[i,k] @ W[j,k]^T      # matmul
            else:
                temp = X[i,k] @ W[j,k]^T        # matmul to temp
                Z[i,j] += temp                  # VPU add (16 elements)
```

**Instruction count for MxM @ MxM tiled matmul:**
- Tiles: (M/4)^3 matmuls
- Accumulations: (M/4)^2 * ((M/4) - 1) * 16 VPU adds
- Example: 8x8 = 8 matmuls + 64 adds = 73 instructions (including HALT)

**Tile-major memory layout:**
Matrices must be stored in tile-major order for efficient access:
```
[tile(0,0), tile(0,1), ..., tile(1,0), tile(1,1), ...]
```
Each tile is stored row-major within the tile (16 contiguous words for 4x4).

## Hardware Constraints

| Constraint | Value | Notes |
|------------|-------|-------|
| IRAM size | 256 instructions | Programs exceeding this fail at compile time |
| BRAM size | 8192 words | 32KB total (fp32) |
| Tile size | 4x4 | Fixed systolic array dimension |
| Max working matrix | 8x8 | Larger matrices exceed instruction limit |

**Execution model:** All instructions must be in a single batch. The TPU does
not support multiple execution phases within one program load. To process
larger workloads, reload data and instructions between compute() calls.
