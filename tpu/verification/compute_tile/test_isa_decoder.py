"""
Tests for decoder.sv aligned with current ISA and SIMD VPU fields.
"""

import cocotb
from cocotb.triggers import Timer
import random

# ISA Mode values
MODE_VPU = 0
MODE_SYSTOLIC = 1
MODE_VADD = 2
MODE_HALT = 3

def encode_vpu_simd_instruction(addr_a, addr_b, addr_out, vpu_type, vreg_dst, vreg_a, vreg_b, vpu_opcode, scalar_b):
    """Encode a VPU SIMD instruction per current decoder.sv."""
    instr = 0
    instr |= (MODE_VPU & 0x3) << 62         # MODE [63:62]
    instr |= (addr_a & 0x1FFF) << 49        # ADDR_A [61:49]
    instr |= (addr_b & 0x1FFF) << 36        # ADDR_B [48:36]
    instr |= (addr_out & 0x1FFF) << 23      # ADDR_OUT [35:23]
    instr |= (vpu_type & 0x7) << 20         # VPU_TYPE [22:20]
    instr |= (vreg_dst & 0x7) << 17         # VREG_DST [19:17]
    instr |= (vreg_a & 0x7) << 14           # VREG_A [16:14]
    instr |= (vreg_b & 0x7) << 11           # VREG_B [13:11]
    instr |= (vpu_opcode & 0x7) << 4        # VPU_OPCODE [6:4]
    instr |= (scalar_b & 0x1) << 3          # SCALAR_B [3]
    return instr


def encode_systolic_instruction(addr_a, addr_b, addr_out, length):
    """Encode a Systolic instruction per ISA spec."""
    instr = 0
    instr |= (MODE_SYSTOLIC & 0x3) << 62    # MODE [63:62]
    instr |= (addr_a & 0x1FFF) << 49        # ADDR_A [61:49]
    instr |= (addr_b & 0x1FFF) << 36        # ADDR_B [48:36]
    instr |= (addr_out & 0x1FFF) << 23      # ADDR_OUT [35:23]
    instr |= (length & 0x7FFFFF)            # LEN [22:0]
    return instr


def encode_halt_instruction():
    """Encode a HALT instruction."""
    return (MODE_HALT & 0x3) << 62


@cocotb.test()
async def test_vpu_simd_add_instruction(dut):
    """Test VPU SIMD ADD instruction decoding."""
    instr = encode_vpu_simd_instruction(
        addr_a=0x100, addr_b=0x200, addr_out=0x300,
        vpu_type=3, vreg_dst=2, vreg_a=0, vreg_b=1,
        vpu_opcode=0, scalar_b=0
    )
    dut.instr_decode.value = instr
    await Timer(1, unit="ns")
    
    assert int(dut.mode_decode.value) == MODE_VPU, "Mode mismatch"
    assert int(dut.addr_a_decode.value) == 0x100, "ADDR_A mismatch"
    assert int(dut.vpu_type_decode.value) == 3, "VPU_TYPE mismatch"
    assert int(dut.vpu_opcode_decode.value) == 0, "VPU_OPCODE mismatch"
    dut._log.info("PASS: VPU SIMD instruction")


@cocotb.test()
async def test_systolic_instruction(dut):
    """Test Systolic (matmul) instruction decoding."""
    instr = encode_systolic_instruction(
        addr_a=0x000, addr_b=0x100, addr_out=0x200, length=16
    )
    dut.instr_decode.value = instr
    await Timer(1, unit="ns")
    
    assert int(dut.mode_decode.value) == MODE_SYSTOLIC, "Mode mismatch"
    assert int(dut.addr_a_decode.value) == 0x000, "ADDR_A mismatch"
    assert int(dut.len_decode.value) == 16, "Length mismatch"
    dut._log.info("PASS: Systolic instruction")


@cocotb.test()
async def test_halt_instruction(dut):
    """Test HALT instruction decoding."""
    instr = encode_halt_instruction()
    dut.instr_decode.value = instr
    await Timer(1, unit="ns")
    
    assert int(dut.mode_decode.value) == MODE_HALT, "Mode mismatch"
    dut._log.info("PASS: HALT instruction")


@cocotb.test()
async def test_full_address_range(dut):
    """Test maximum address values."""
    max_addr = 0x1FFF
    instr = encode_systolic_instruction(max_addr, max_addr, max_addr, 0)
    dut.instr_decode.value = instr
    await Timer(1, unit="ns")
    
    assert int(dut.addr_a_decode.value) == max_addr
    assert int(dut.addr_b_decode.value) == max_addr
    assert int(dut.addr_out_decode.value) == max_addr
    dut._log.info("PASS: Full address range test")
