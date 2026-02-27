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


@cocotb.test()
async def test_tensorcore_vpu_data_flow(dut):
    """Test VLOAD→VSTORE identity: data loaded and stored without modification.

    Program: [vload(V0, addr=100), vstore(V0, addr=200), halt]
    BRAM[100:107] pre-populated with known values.
    Verifies BRAM[200:207] == original BRAM[100:107] after execution.

    Instruction encoding uses decoder.sv hardware format ([63:62]=mode):
      VLOAD  V0, addr=100: mode=0, addr_a=100, vpu_type=1, vreg_dst=0
      VSTORE V0, addr=200: mode=0, addr_out=200, vpu_type=2, vreg_a=0
      HALT:                mode=3
    """
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

    # BRAM model: pre-populate addresses 100–107 with known values
    bram = {}
    src_vals = [float(i * 3 + 1) for i in range(8)]  # [1.0, 4.0, 7.0, ...]
    for i in range(8):
        bram[100 + i] = float_to_fp32(src_vals[i])

    # Encode instructions (decoder.sv hardware format: mode=[63:62])
    vload_instr  = (100 << 49) | (1 << 20)          # addr_a=100, vpu_type=1, vreg_dst=0
    vstore_instr = (200 << 23) | (2 << 20)           # addr_out=200, vpu_type=2, vreg_a=0
    halt_instr   = 3 << 62

    # Load program into IRAM
    instructions = [vload_instr, vstore_instr, halt_instr]
    for i, instr in enumerate(instructions):
        dut.iram_addr.value = i
        dut.dma_iram_din.value = instr
        dut.instr_write_en.value = 1
        await RisingEdge(dut.clk)
    dut.instr_write_en.value = 0
    await RisingEdge(dut.clk)

    # Start execution
    dut.start.value = 1
    await RisingEdge(dut.clk)
    dut.start.value = 0

    # Run until done, serving BRAM Port B requests from the model
    done_found = False
    for _ in range(1000):
        await RisingEdge(dut.clk)
        if int(dut.bram_en_b.value) == 1 and int(dut.bram_we_b.value) == 0:
            addr = int(dut.bram_addr_b.value)
            dut.bram_dout_b.value = bram.get(addr, 0)
        elif int(dut.bram_en_b.value) == 1 and int(dut.bram_we_b.value) == 1:
            bram[int(dut.bram_addr_b.value)] = int(dut.bram_din_b.value)
        if int(dut.done.value) == 1:
            done_found = True
            break

    assert done_found, "TensorCore should complete within timeout"

    # Verify identity: BRAM[200:207] == original BRAM[100:107]
    for i in range(8):
        addr = 200 + i
        assert addr in bram, f"Missing BRAM write at address {addr} (VSTORE did not fire)"
        got = fp32_to_float(bram[addr])
        exp = src_vals[i]
        assert abs(got - exp) < 1e-4, \
            f"Data mismatch at BRAM[{addr}]: expected {exp}, got {got}"

    dut._log.info("PASS: test_tensorcore_vpu_data_flow — VLOAD→VSTORE identity verified")
