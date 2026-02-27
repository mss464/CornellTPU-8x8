"""
Unit tests for decoder.sv - Instruction decoder for the TPU
Tests instruction field extraction with various instruction patterns
"""

import cocotb
from cocotb.triggers import Timer
import random


def create_instruction(mode=0, addr_a=0, addr_b=0, addr_out=0, len_val=0):
    """
    Create a 64-bit instruction from fields.
    Instruction format (from decoder.sv):
    - [22:0]   len_decode
    - [35:23]  addr_out_decode
    - [48:36]  addr_b_decode
    - [61:49]  addr_a_decode
    - [63:62]  mode_decode
    """
    instr = 0
    instr |= (len_val & 0x7FFFFF)         # bits [22:0]
    instr |= (addr_out & 0x1FFF) << 23   # bits [35:23]
    instr |= (addr_b & 0x1FFF) << 36     # bits [48:36]
    instr |= (addr_a & 0x1FFF) << 49     # bits [61:49]
    instr |= (mode & 0x3) << 62          # bits [63:62]
    return instr


@cocotb.test()
async def test_decoder_zero_instruction(dut):
    """Test decoder with all-zero instruction."""
    dut.instr_decode.value = 0
    await Timer(1, unit="ns")

    assert int(dut.mode_decode.value) == 0, "Mode should be 0"
    assert int(dut.addr_a_decode.value) == 0, "Addr A should be 0"
    assert int(dut.addr_b_decode.value) == 0, "Addr B should be 0"
    assert int(dut.addr_out_decode.value) == 0, "Addr Out should be 0"
    assert int(dut.len_decode.value) == 0, "Length should be 0"

    dut._log.info("PASS: Zero instruction test")


@cocotb.test()
async def test_decoder_max_values(dut):
    """Test decoder with maximum field values."""
    # Set all fields to their maximum values
    max_mode = 0x3          # 2 bits
    max_addr = 0x1FFF       # 13 bits
    max_len = 0x7FFFFF      # 23 bits

    instr = create_instruction(
        mode=max_mode,
        addr_a=max_addr,
        addr_b=max_addr,
        addr_out=max_addr,
        len_val=max_len
    )

    dut.instr_decode.value = instr
    await Timer(1, unit="ns")

    assert int(dut.mode_decode.value) == max_mode, f"Mode mismatch: got {int(dut.mode_decode.value)}, expected {max_mode}"
    assert int(dut.addr_a_decode.value) == max_addr, f"Addr A mismatch"
    assert int(dut.addr_b_decode.value) == max_addr, f"Addr B mismatch"
    assert int(dut.addr_out_decode.value) == max_addr, f"Addr Out mismatch"
    assert int(dut.len_decode.value) == max_len, f"Length mismatch"

    dut._log.info("PASS: Max values test")


@cocotb.test()
async def test_decoder_mode_field(dut):
    """Test decoder mode field isolation."""
    for mode in range(4):
        instr = create_instruction(mode=mode)
        dut.instr_decode.value = instr
        await Timer(1, unit="ns")

        decoded_mode = int(dut.mode_decode.value)
        assert decoded_mode == mode, f"Mode mismatch: got {decoded_mode}, expected {mode}"

    dut._log.info("PASS: Mode field test")


@cocotb.test()
async def test_decoder_address_fields(dut):
    """Test decoder address field isolation."""
    test_addresses = [0x0, 0x1, 0x100, 0x555, 0xAAA, 0x1FFF]

    for addr in test_addresses:
        # Test addr_a
        instr = create_instruction(addr_a=addr)
        dut.instr_decode.value = instr
        await Timer(1, unit="ns")
        assert int(dut.addr_a_decode.value) == addr, f"Addr A mismatch for {addr:#x}"

        # Test addr_b
        instr = create_instruction(addr_b=addr)
        dut.instr_decode.value = instr
        await Timer(1, unit="ns")
        assert int(dut.addr_b_decode.value) == addr, f"Addr B mismatch for {addr:#x}"

        # Test addr_out
        instr = create_instruction(addr_out=addr)
        dut.instr_decode.value = instr
        await Timer(1, unit="ns")
        assert int(dut.addr_out_decode.value) == addr, f"Addr Out mismatch for {addr:#x}"

    dut._log.info("PASS: Address fields test")


@cocotb.test()
async def test_decoder_randomized(dut):
    """Randomized test for decoder with random instructions."""
    num_tests = 50
    seed = 12345
    random.seed(seed)

    dut._log.info(f"Starting randomized decoder test with {num_tests} instructions (seed={seed})")

    for test_num in range(num_tests):
        # Generate random field values
        mode = random.randint(0, 3)
        addr_a = random.randint(0, 0x1FFF)
        addr_b = random.randint(0, 0x1FFF)
        addr_out = random.randint(0, 0x1FFF)
        len_val = random.randint(0, 0x7FFFFF)

        instr = create_instruction(
            mode=mode,
            addr_a=addr_a,
            addr_b=addr_b,
            addr_out=addr_out,
            len_val=len_val
        )

        dut.instr_decode.value = instr
        await Timer(1, unit="ns")

        # Verify all fields
        assert int(dut.mode_decode.value) == mode, f"Test {test_num}: Mode mismatch"
        assert int(dut.addr_a_decode.value) == addr_a, f"Test {test_num}: Addr A mismatch"
        assert int(dut.addr_b_decode.value) == addr_b, f"Test {test_num}: Addr B mismatch"
        assert int(dut.addr_out_decode.value) == addr_out, f"Test {test_num}: Addr Out mismatch"
        assert int(dut.len_decode.value) == len_val, f"Test {test_num}: Length mismatch"

    dut._log.info(f"PASS: Randomized decoder test completed ({num_tests} instructions)")


@cocotb.test()
async def test_decoder_typical_instructions(dut):
    """Test decoder with typical TPU instruction patterns."""
    # MATMUL: mode=0, addresses set
    matmul_instr = create_instruction(
        mode=0,
        addr_a=0x100,
        addr_b=0x200,
        addr_out=0x300,
        len_val=0x01
    )
    dut.instr_decode.value = matmul_instr
    await Timer(1, unit="ns")
    assert int(dut.mode_decode.value) == 0
    assert int(dut.addr_a_decode.value) == 0x100
    assert int(dut.addr_b_decode.value) == 0x200
    assert int(dut.addr_out_decode.value) == 0x300

    # LOAD: mode=1
    load_instr = create_instruction(
        mode=1,
        addr_a=0x400,
        addr_out=0x500,
        len_val=0x02
    )
    dut.instr_decode.value = load_instr
    await Timer(1, unit="ns")
    assert int(dut.mode_decode.value) == 1
    assert int(dut.addr_a_decode.value) == 0x400
    assert int(dut.addr_out_decode.value) == 0x500

    # STORE: mode=2
    store_instr = create_instruction(
        mode=2,
        addr_a=0x600,
        addr_out=0x700,
        len_val=0x03
    )
    dut.instr_decode.value = store_instr
    await Timer(1, unit="ns")
    assert int(dut.mode_decode.value) == 2

    # NOP/HALT: mode=3
    halt_instr = create_instruction(mode=3, len_val=0x000)
    dut.instr_decode.value = halt_instr
    await Timer(1, unit="ns")
    assert int(dut.mode_decode.value) == 3

    dut._log.info("PASS: Typical instructions test")
