import cocotb
from cocotb.triggers import RisingEdge, Timer
from cocotb.clock import Clock
import struct

def float_to_fp32(f):
    return struct.unpack('>I', struct.pack('>f', f))[0]

@cocotb.test()
async def test_tensorcore_halt(dut):
    """Test that TensorCore can fetch and execute a HALT instruction."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.instr_write_en.value = 0
    dut.iram_addr.value = 0
    dut.dma_iram_din.value = 0
    dut.bram_dout_b.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Load HALT instruction (mode=3) into I-RAM at addr 0
    # mode is at [63:62]
    halt_instr = 3 << 62
    
    dut.iram_addr.value = 0
    dut.dma_iram_din.value = halt_instr
    dut.instr_write_en.value = 1
    await RisingEdge(dut.clk)
    dut.instr_write_en.value = 0
    await RisingEdge(dut.clk)

    # Start execution
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Wait for done
    # FSM: IDLE -> EXEC_COMPUTE (halt) -> HALT_STATE -> done=1
    # Should take a few cycles
    done_found = False
    for _ in range(50):
        await RisingEdge(dut.clk)
        if int(dut.done.value) == 1:
            done_found = True
            break
    
    assert done_found, "TensorCore should have reached HALT state"
    dut._log.info("PASS: TensorCore HALT instruction executed")

@cocotb.test()
async def test_tensorcore_vload_vhalt(dut):
    """Test VLOAD followed by HALT."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.instr_write_en.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    # Instruction 0: VLOAD (mode=0, vpu_type=1)
    # mode [63:62] = 0
    # addr_a [61:49] = 100
    # vpu_type [22:20] = 1
    # vreg_dst [19:17] = 0
    vload_instr = (100 << 49) | (1 << 20) | (0 << 17)
    
    # Instruction 1: HALT (mode=3)
    halt_instr = 3 << 62

    # Load instructions
    instructions = [vload_instr, halt_instr]
    for i, instr in enumerate(instructions):
        dut.iram_addr.value = i
        dut.dma_iram_din.value = instr
        dut.instr_write_en.value = 1
        await RisingEdge(dut.clk)
    dut.instr_write_en.value = 0
    await RisingEdge(dut.clk)

    # Start
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Wait for completion
    done_found = False
    for _ in range(200):
        await RisingEdge(dut.clk)
        if int(dut.done.value) == 1:
            done_found = True
            break
    
    assert done_found, "TensorCore should have completed execution"
    dut._log.info("PASS: TensorCore VLOAD + HALT sequence executed")
