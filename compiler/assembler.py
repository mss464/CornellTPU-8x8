
import sys
import ast
import os
import shutil
import numpy as np

# Updated template using compiler.hal.pynq_host
HOST_TEMPLATE = """
import argparse
import sys
import time
import os
import numpy as np

# Add compiler path if needed, assuming running from tests/fpga or similar
# sys.path.append(...)

try:
    from compiler.hal.pynq_host import TpuDriver
except ImportError as e:
    # Fallback for development/simulation
    print(f"Warning: Could not import TpuDriver: {e}")
    TpuDriver = None

# --- Auto-injected ---
LOADS = __LOADS__
STORES = __STORES__

def main():
    parser = argparse.ArgumentParser(description="Generated TPU Test Script")
    parser.add_argument("bitstream", type=str, help="Path to TPU bitstream (.bit)")
    parser.add_argument("instr_file", type=str, help="Path to instruction file")
    args = parser.parse_args()

    if not os.path.exists(args.bitstream):
        raise FileNotFoundError(f"Cannot find {args.bitstream}")
    if not os.path.exists(args.instr_file):
        raise FileNotFoundError(f"Cannot find {args.instr_file}")

    print(f"Programming FPGA with {args.bitstream}")
    tpu = TpuDriver(args.bitstream)

    bench = {
        "load_time": 0.0,
        "write_iram_time": 0.0,
        "compute_time": 0.0,
        "store_time": 0.0,
        "total_time": 0.0
    }

    overall_start = time.perf_counter()

    # Load data to BRAM
    print("Loading data...")
    t0 = time.perf_counter()
    for addr, length, values in LOADS:
        # values is a list
        tpu.write_bram(addr, np.array(values, dtype=np.float32))
    bench["load_time"] = time.perf_counter() - t0
    print("loading data complete")

    # Load instructions
    print("Loading instructions...")
    instrs = []
    with open(args.instr_file) as f:
        for line in f:
            line = line.strip()
            if line:
                instrs.append(int(line, 16))
    instrs_np = np.array(instrs, dtype=np.uint64)

    t0 = time.perf_counter()
    tpu.write_instructions(instrs_np)
    bench["write_iram_time"] = time.perf_counter() - t0
    print("writing instructions complete")

    # Execute compute
    print("Executing compute...")
    t0 = time.perf_counter()
    tpu.compute()
    bench["compute_time"] = time.perf_counter() - t0
    print("compute complete")

    # Read back results
    print("Reading results...")
    t0 = time.perf_counter()
    for addr, length, label in STORES:
        result = tpu.read_bram(addr, length)
        print(f"{label} = {result}")
    bench["store_time"] = time.perf_counter() - t0
    print("storing complete")

    bench["total_time"] = time.perf_counter() - overall_start

    print("===== BENCHMARK RESULTS =====")
    for key, val in bench.items():
        print(f"{key}: {val*1000:.3f} ms")

if __name__ == "__main__":
    main()
"""


OPCODES_VPU = {
    "add": 0,
    "sub": 1,
    "relu": 2,
    "mul": 3,
    "relu_derivative": 4,
}

# VPU SIMD opcodes (3-bit encoding)
OPCODES_VCOMPUTE = {
    "vadd": 0,    # vpu_op ADD
    "vsub": 1,    # vpu_op SUB
    "vrelu": 2,   # vpu_op RELU
    "vmul": 3,    # vpu_op MUL
    "vmax": 4,
    "vmin": 5,
}

# VPU_TYPE field values
VPU_TYPE_SCALAR = 0
VPU_TYPE_VLOAD = 1
VPU_TYPE_VSTORE = 2
VPU_TYPE_VCOMPUTE = 3

MODE_VPU      = 0
MODE_SYSTOLIC = 1
MODE_RESERVED = 2
MODE_HALT     = 3

ADDR_BITS   = 13
LEN_BITS    = 23
OPCODE_BITS = 10

ADDR_MAX   = (1 << ADDR_BITS) - 1
LEN_MAX    = (1 << LEN_BITS) - 1
OPCODE_MAX = (1 << OPCODE_BITS) - 1

# Instruction memory limit (hardware constraint)
IMEM_MAX_SIZE = 256


class CompilationError(Exception):
    """Raised when compilation fails due to hardware constraints."""
    pass

LOADS = []
STORES = []

LOADS_OPTIMIZED = []
STORES_OPTIMIZED = []

MEMORY_SIZE = 8192  


def check_addr(addr: int, label: str):
    if not (0 <= addr <= ADDR_MAX):
        raise ValueError(f"{label} address {addr} out of range (0..{ADDR_MAX})")
    return addr


def check_vreg(vreg: int, name: str):
    """Validate vector register ID (0-7)."""
    if not (0 <= vreg <= 7):
        raise ValueError(f"{name} {vreg} out of range (0-7)")
    return vreg


def encode_vpu(op: str, addr_a: int, addr_b: int, addr_out: int, addr_const: int = 0):
    opcode = OPCODES_VPU[op]
    check_addr(addr_a, "addr_a")
    check_addr(addr_b, "addr_b")
    check_addr(addr_out, "addr_out")
    check_addr(addr_const, "addr_const")

    word = 0
    word |= (MODE_VPU & 0b11) << 62
    word |= (addr_a & ADDR_MAX) << 49
    word |= (addr_b & ADDR_MAX) << 36
    word |= (addr_out & ADDR_MAX) << 23
    word |= (addr_const & ADDR_MAX) << 10
    word |= (opcode & OPCODE_MAX)

    return word


def encode_systolic(addr_a: int, addr_b: int, addr_out: int, length: int):
    check_addr(addr_a, "addr_a")
    check_addr(addr_b, "addr_b")
    check_addr(addr_out, "addr_out")
    if not (0 <= length <= LEN_MAX):
        raise ValueError(f"length {length} out of range")

    word = 0
    word |= (MODE_SYSTOLIC & 0b11) << 62
    word |= (addr_a & ADDR_MAX) << 49
    word |= (addr_b & ADDR_MAX) << 36
    word |= (addr_out & ADDR_MAX) << 23
    word |= (length & LEN_MAX)

    return word


def encode_halt():
    word = 0
    word |= (MODE_HALT & 0b11) << 62
    return word


def encode_vload(vreg_dst: int, addr: int):
    """
    Encode VLOAD instruction.

    Args:
        vreg_dst: Destination vector register (0-7)
        addr: BRAM start address (13 bits)

    Returns:
        64-bit instruction word
    """
    check_vreg(vreg_dst, "vreg_dst")
    check_addr(addr, "addr")

    word = 0
    word |= (MODE_VPU & 0b11) << 62
    word |= (addr & ADDR_MAX) << 49
    word |= (VPU_TYPE_VLOAD & 0b111) << 20
    word |= (vreg_dst & 0b111) << 17
    return word


def encode_vstore(vreg_src: int, addr: int):
    """
    Encode VSTORE instruction.

    Args:
        vreg_src: Source vector register (0-7)
        addr: BRAM destination address (13 bits)

    Returns:
        64-bit instruction word
    """
    check_vreg(vreg_src, "vreg_src")
    check_addr(addr, "addr")

    word = 0
    word |= (MODE_VPU & 0b11) << 62
    word |= (addr & ADDR_MAX) << 49
    word |= (VPU_TYPE_VSTORE & 0b111) << 20
    word |= (vreg_src & 0b111) << 14
    return word


def encode_vcompute(op: str, vreg_dst: int, vreg_a: int, vreg_b: int = 0, scalar_b: bool = False):
    """
    Encode VCOMPUTE instruction.

    Args:
        op: Operation name (vadd, vsub, vmul, vrelu, etc.)
        vreg_dst: Destination register (0-7)
        vreg_a: Source register A (0-7)
        vreg_b: Source register B (0-7), or scalar source if scalar_b=True
        scalar_b: If True, broadcast vreg_b[0] to all lanes

    Returns:
        64-bit instruction word
    """
    opcode = OPCODES_VCOMPUTE[op]
    check_vreg(vreg_dst, "vreg_dst")
    check_vreg(vreg_a, "vreg_a")
    check_vreg(vreg_b, "vreg_b")

    word = 0
    word |= (MODE_VPU & 0b11) << 62
    word |= (VPU_TYPE_VCOMPUTE & 0b111) << 20
    word |= (vreg_dst & 0b111) << 17
    word |= (vreg_a & 0b111) << 14
    word |= (vreg_b & 0b111) << 11
    word |= (opcode & 0b111) << 4
    word |= (1 if scalar_b else 0) << 3
    return word


def parse_int_token(tok: str) -> int:
    tok = tok.strip().rstrip(",")
    if tok.startswith("0x") or tok.startswith("0X"):
        return int(tok, 16)
    return int(tok)


def assemble_line(line: str, matmul_len: int = 16):
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    
    
    parts = line.split(maxsplit=1)
    op = parts[0].lower()

      # ----------- LOAD HANDLING ----------
    if op == "load":
        # Format: load <addr>, <length>, <python_literal>

        addr_str, length_str, values_str = parts[1].split(",", 2)
        addr = parse_int_token(addr_str)
        length = parse_int_token(length_str)
        values = ast.literal_eval(values_str.strip())
        LOADS.append((addr, length, values))
        return None

    # ----------- STORE HANDLING ----------
    if op == "store":

        addr_str, length_str, label_str = parts[1].split(",", 2)
        addr = parse_int_token(addr_str)
        length = parse_int_token(length_str)
        label = label_str.strip()

        STORES.append((addr, length, label))
        return None

    tokens = line.split()
    op = parts[0].lower()
    operands = [parse_int_token(p) for p in tokens[1:]]
    

    if op == "matmul":
        if len(operands) != 3:
            raise ValueError(f"matmul expects 3 operands: {line}")
        return encode_systolic(*operands, matmul_len)

    if op == "halt":
        return encode_halt()

    if op in OPCODES_VPU:
        if len(operands) != 3:
            raise ValueError(f"{op} expects 3 operands: {line}")
        return encode_vpu(op, *operands)

    raise ValueError(f"Unknown op: {op}")

def generate_host_py(host_path, loads, stores):
    with open(host_path, "w") as f:
        template = HOST_TEMPLATE.replace(
            "__LOADS__", repr(loads)
        ).replace(
            "__STORES__", repr(stores)
        )
        f.write(template)


def assemble_file(input_path: str, output_path: str, matmul_len: int = 16):
    
    # clear global lists for fresh run
    LOADS.clear()
    STORES.clear()

    with open(input_path, "r") as f:
        lines = f.readlines()

    assembled_words = []

    for line in lines:
        encoded = assemble_line(line, matmul_len)
        if encoded is not None:
            assembled_words.append(encoded)

    # Always append HALT as the final instruction
    assembled_words.append(encode_halt())

    # Check instruction memory limit
    if len(assembled_words) > IMEM_MAX_SIZE:
        raise CompilationError(
            f"Program has {len(assembled_words)} instructions, exceeds IMEM limit of {IMEM_MAX_SIZE}. "
            f"Consider using tiled operations to reduce instruction count."
        )

    with open(output_path, "w") as f:
        for word in assembled_words:
            f.write(f"{word:016X}\n")

    print(f"Assembly complete. Wrote {len(assembled_words)} instructions to {output_path}")

    # Generate host code in the same directory as output_path named "test_generated.py"
    # or just assume output_path dir
    
    output_dir = os.path.dirname(os.path.abspath(output_path))
    host_py_path = os.path.join(output_dir, "test_generated.py")
    
    generate_host_py(host_py_path, LOADS, STORES)
    print(f"Generated host script: {host_py_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python assemble.py input.txt output.txt [matmul_len]")
        sys.exit(1)
    
    matmul_len = 16
    if len(sys.argv) > 3:
        matmul_len = int(sys.argv[3])

    assemble_file(sys.argv[1], sys.argv[2], matmul_len)
