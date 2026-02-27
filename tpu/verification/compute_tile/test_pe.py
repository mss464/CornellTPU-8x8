import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, Timer
import struct
import math

def to_fixed(val, frac_bits=8):
    return int(round(val * (1 << frac_bits))) & 0xFFFF

def from_fixed(val, frac_bits=8):
    if val >= (1 << 15):
        val -= (1 << 16)
    return float(val) / (1 << frac_bits)

def float_to_fp32_bits(val: float) -> int:
    return struct.unpack(">I", struct.pack(">f", float(val)))[0]

def fp32_bits_to_float(bits: int) -> float:
    bits = bits & 0xFFFFFFFF
    return struct.unpack(">f", struct.pack(">I", bits))[0]

def bits_is_nan(bits: int) -> bool:
    return ((bits & 0x7F800000) == 0x7F800000) and ((bits & 0x007FFFFF) != 0)

def bits_is_inf(bits: int) -> bool:
    return ((bits & 0x7F800000) == 0x7F800000) and ((bits & 0x007FFFFF) == 0)


async def apply_mac_and_sample(dut, a_bits: int, psum_bits: int):
    """Apply inputs with pe_valid_in=1 and sample output on next cycle."""
    dut.pe_valid_in.value = 1
    dut.pe_input_in.value = a_bits
    dut.pe_psum_in.value = psum_bits
    await RisingEdge(dut.clk)
    # Wait a delta to allow NBA updates to settle
    await Timer(1, unit="ps")
    return int(dut.pe_psum_out.value)

@cocotb.test()
async def test_pe(dut):
    """Test the PE module with a variety of fixed-point inputs."""

    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.rst_n.value = 0
    dut.pe_valid_in.value = 0 # this would enable the PE to start processing the inputs. but it doesnt here

    dut.pe_enabled.value = 1
    dut.pe_accept_w_in.value = 0
    dut.pe_input_in.value = to_fixed(0.0)
    dut.pe_weight_in.value = to_fixed(0.0)
    dut.pe_psum_in.value = to_fixed(0.0)
    await RisingEdge(dut.clk)

    # Release reset
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # t = 0: Stage the weights
    dut.pe_accept_w_in.value = 1; # THIS IS THE "A" in xander's drawing!
    dut.pe_weight_in.value = to_fixed(69.0) # in next cycle, gets latched in background buffer of pe11!
    await RisingEdge(dut.clk)


    # t = 1: Weight should now be loaded in background buffer
    dut.pe_accept_w_in.value = 1 # on next clock cycle 10 should be latched in background buffer of pe21, 20 should be latched in background buffer of pe 11!
    dut.pe_weight_in.value = to_fixed(10.0)
    await RisingEdge(dut.clk)

    # t = 2: Assert the pe_switch_out signal to bring weight from bb to fb (foreground buffer) in next cycle
    dut.pe_accept_w_in.value = 0 # stop loading weights into background buffer. 
    dut.pe_switch_in.value = 1 # bring weight from bb to fb in next cc
    dut.pe_valid_in.value = 1 # we want inputs to start moving in next cc, so we assert this flag here. 
    dut.pe_input_in.value = to_fixed(2.0)
    dut.pe_psum_in.value = to_fixed(50.0) 
    await RisingEdge(dut.clk)

    dut.pe_valid_in.value = 1
    await RisingEdge(dut.clk)

    dut.pe_valid_in.value = 0
    await RisingEdge(dut.clk)

    # t = 3: 
    # in this clock cycle, pe_valid_in and pe_switch_in are latched into pe11, now they are asserted to the outside of pe12 and pe21
    # pe11 should also output a psum here, and pass its input to pe12
    
    # pe_switch_in and pe_valid_in should also be zero here 
    # I HAVE MANUALLY DEFINED pe_switch_in AND pe_valid_in ZERO here. This is decided by the compiler.

    dut.pe_switch_in.value = 0 # bring weight from bb to fb in next cc
    dut.pe_valid_in.value = 0 # we want inputs to start moving in next cc, so we assert this flag here. 


    await ClockCycles(dut.clk, 3)


@cocotb.test()
async def test_pe_fp32_extremes_and_signs(dut):
    """FP32 edge cases: max/min/inf/nan and sign handling."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.rst_n.value = 0
    dut.pe_enabled.value = 1
    dut.pe_valid_in.value = 0
    dut.pe_accept_w_in.value = 0
    dut.pe_switch_in.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    max_f = float("3.4028235e38")
    min_n = float("1.17549435e-38")
    pos_inf = float("inf")
    neg_inf = float("-inf")
    nan = float("nan")

    # Load weight directly into active (accept + switch same cycle)
    dut.pe_accept_w_in.value = 1
    dut.pe_switch_in.value = 1
    dut.pe_weight_in.value = float_to_fp32_bits(max_f)
    await RisingEdge(dut.clk)
    dut.pe_accept_w_in.value = 0
    dut.pe_switch_in.value = 0

    # Compute after weight is active
    res_bits = await apply_mac_and_sample(
        dut, float_to_fp32_bits(max_f), float_to_fp32_bits(0.0)
    )
    # Expect overflow -> inf
    assert bits_is_inf(res_bits), f"max*max expected inf, got 0x{res_bits:08x}"

    # NaN propagation
    res_bits = await apply_mac_and_sample(
        dut, float_to_fp32_bits(nan), float_to_fp32_bits(1.0)
    )
    assert bits_is_nan(res_bits), f"NaN input expected NaN, got 0x{res_bits:08x}"

    # inf * 0 -> NaN
    dut.pe_input_in.value = float_to_fp32_bits(pos_inf)
    dut.pe_weight_in.value = float_to_fp32_bits(0.0)
    dut.pe_accept_w_in.value = 1
    dut.pe_switch_in.value = 1
    await RisingEdge(dut.clk)
    dut.pe_accept_w_in.value = 0
    dut.pe_switch_in.value = 0
    await RisingEdge(dut.clk)
    res_bits = await apply_mac_and_sample(
        dut, float_to_fp32_bits(pos_inf), float_to_fp32_bits(0.0)
    )
    assert bits_is_nan(res_bits), f"inf*0 expected NaN, got 0x{res_bits:08x}"

    # Sign check: (-inf) * (1) + 0 -> -inf
    dut.pe_input_in.value = float_to_fp32_bits(neg_inf)
    dut.pe_weight_in.value = float_to_fp32_bits(1.0)
    dut.pe_accept_w_in.value = 1
    dut.pe_switch_in.value = 1
    await RisingEdge(dut.clk)
    dut.pe_accept_w_in.value = 0
    dut.pe_switch_in.value = 0
    await RisingEdge(dut.clk)
    res_bits = await apply_mac_and_sample(
        dut, float_to_fp32_bits(neg_inf), float_to_fp32_bits(0.0)
    )
    assert bits_is_inf(res_bits) and (res_bits & 0x80000000), f"-inf expected, got 0x{res_bits:08x}"


@cocotb.test()
async def test_pe_back_to_back_valid(dut):
    """Back-to-back pe_valid_in pulses should process consecutive cycles."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.pe_enabled.value = 1
    dut.pe_valid_in.value = 0
    dut.pe_accept_w_in.value = 0
    dut.pe_switch_in.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Load weight = 2.0 directly into active
    dut.pe_accept_w_in.value = 1
    dut.pe_switch_in.value = 1
    dut.pe_weight_in.value = float_to_fp32_bits(2.0)
    await RisingEdge(dut.clk)
    dut.pe_accept_w_in.value = 0
    dut.pe_switch_in.value = 0
    await RisingEdge(dut.clk)

    # Two consecutive inputs
    res1 = fp32_bits_to_float(
        await apply_mac_and_sample(dut, float_to_fp32_bits(3.0), float_to_fp32_bits(1.0))
    )
    res2 = fp32_bits_to_float(
        await apply_mac_and_sample(dut, float_to_fp32_bits(4.0), float_to_fp32_bits(1.0))
    )

    assert abs(res1 - (3.0 * 2.0 + 1.0)) < 1e-3, f"res1 {res1}"
    assert abs(res2 - (4.0 * 2.0 + 1.0)) < 1e-3, f"res2 {res2}"


@cocotb.test()
async def test_pe_enable_disable(dut):
    """Disabling pe_enabled should clear outputs and registers."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.pe_enabled.value = 1
    dut.pe_valid_in.value = 0
    dut.pe_accept_w_in.value = 0
    dut.pe_switch_in.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Load weight
    dut.pe_accept_w_in.value = 1
    dut.pe_weight_in.value = float_to_fp32_bits(5.0)
    await RisingEdge(dut.clk)
    dut.pe_accept_w_in.value = 0
    dut.pe_switch_in.value = 1
    await RisingEdge(dut.clk)
    dut.pe_switch_in.value = 0

    # Disable
    dut.pe_enabled.value = 0
    dut.pe_valid_in.value = 1
    dut.pe_input_in.value = float_to_fp32_bits(2.0)
    dut.pe_psum_in.value = float_to_fp32_bits(1.0)
    await RisingEdge(dut.clk)
    assert int(dut.pe_psum_out.value) == 0, "Output should clear when disabled"
    assert int(dut.pe_valid_out.value) == 0, "Valid should clear when disabled"

    
