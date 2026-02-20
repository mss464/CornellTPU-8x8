"""
Unit tests for kernel abstraction.

Tests:
1. Param arithmetic: Param + offset resolves correctly
2. Compilation: kernel produces correct instruction count
3. Resolution: symbolic instructions resolve to expected uint64 values
"""

import sys
from pathlib import Path
# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
import numpy as np

from compiler.kernel import (
    Param, SymbolicInstruction, CompiledKernel,
    KernelCompiler, kernel
)
from compiler.assembler import encode_systolic, encode_vpu


class TestParam:
    """Tests for Param symbolic address class."""

    def test_param_creation(self):
        p = Param("X")
        assert p.name == "X"
        assert p.offset == 0

    def test_param_add(self):
        p = Param("X")
        p2 = p + 5
        assert p2.name == "X"
        assert p2.offset == 5
        # Original unchanged
        assert p.offset == 0

    def test_param_add_reverse(self):
        p = Param("X")
        p2 = 5 + p
        assert p2.name == "X"
        assert p2.offset == 5

    def test_param_sub(self):
        p = Param("X", offset=10)
        p2 = p - 3
        assert p2.name == "X"
        assert p2.offset == 7

    def test_param_chained_arithmetic(self):
        p = Param("Z")
        p2 = p + 10 + 5 - 3
        assert p2.offset == 12

    def test_param_resolve(self):
        p = Param("W", offset=5)
        bindings = {"W": 100}
        assert p.resolve(bindings) == 105

    def test_param_resolve_missing_binding(self):
        p = Param("X")
        with pytest.raises(ValueError, match="not bound"):
            p.resolve({})

    def test_param_resolve_out_of_range(self):
        p = Param("X", offset=10000)
        with pytest.raises(ValueError, match="out of range"):
            p.resolve({"X": 10000})

    def test_param_repr(self):
        assert "Param('X')" in repr(Param("X"))
        assert "+ 5" in repr(Param("X", 5))
        assert "- 3" in repr(Param("X", -3))


class TestSymbolicInstruction:
    """Tests for SymbolicInstruction resolution."""

    def test_matmul_resolve(self):
        instr = SymbolicInstruction(
            op="matmul",
            operands=(Param("W"), Param("X"), Param("Z"), 16)
        )
        bindings = {"W": 0, "X": 16, "Z": 32}
        resolved = instr.resolve(bindings)
        expected = encode_systolic(0, 16, 32, 16)
        assert resolved == expected

    def test_vpu_add_resolve(self):
        instr = SymbolicInstruction(
            op="add",
            operands=(Param("A"), Param("B"), Param("C"))
        )
        bindings = {"A": 0, "B": 4, "C": 8}
        resolved = instr.resolve(bindings)
        expected = encode_vpu("add", 0, 4, 8)
        assert resolved == expected

    def test_vpu_with_offset(self):
        instr = SymbolicInstruction(
            op="add",
            operands=(Param("A") + 2, Param("B") + 2, Param("C") + 2)
        )
        bindings = {"A": 0, "B": 4, "C": 8}
        resolved = instr.resolve(bindings)
        expected = encode_vpu("add", 2, 6, 10)
        assert resolved == expected


class TestCompiledKernel:
    """Tests for CompiledKernel."""

    def test_resolve_all(self):
        compiled = CompiledKernel(
            name="test_kernel",
            params=["W", "X", "Z"],
            instructions=[
                SymbolicInstruction("matmul", (Param("W"), Param("X"), Param("Z"), 16))
            ]
        )
        bindings = {"W": 0, "X": 16, "Z": 32}
        result = compiled.resolve(bindings)

        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint64
        assert len(result) == 1
        assert result[0] == encode_systolic(0, 16, 32, 16)

    def test_resolve_missing_param(self):
        compiled = CompiledKernel(
            name="test",
            params=["W", "X", "Z"],
            instructions=[]
        )
        with pytest.raises(ValueError, match="Missing bindings"):
            compiled.resolve({"W": 0, "X": 16})  # Missing Z


class TestKernelDecorator:
    """Tests for @kernel decorator and compilation."""

    def test_simple_kernel_compile(self):
        @kernel
        def simple_matmul(W: Param, X: Param, Z: Param):
            from compiler.tpu_txt import matmul
            matmul(W, X, Z)

        compiled = simple_matmul.compile()

        assert compiled.name == "simple_matmul"
        assert compiled.params == ["W", "X", "Z"]
        assert len(compiled.instructions) == 1
        assert compiled.instructions[0].op == "matmul"

    def test_kernel_with_loop(self):
        @kernel
        def vector_add_4(A: Param, B: Param, C: Param):
            from compiler.tpu_txt import add
            for i in range(4):
                add(A + i, B + i, C + i)

        compiled = vector_add_4.compile()

        assert len(compiled.instructions) == 4
        for i, instr in enumerate(compiled.instructions):
            assert instr.op == "add"
            # Check offsets are captured
            assert instr.operands[0].offset == i
            assert instr.operands[1].offset == i
            assert instr.operands[2].offset == i

    def test_kernel_resolution(self):
        @kernel
        def add_kernel(A: Param, B: Param, C: Param):
            from compiler.tpu_txt import add
            add(A, B, C)

        compiled = add_kernel.compile()
        result = compiled.resolve({"A": 0, "B": 4, "C": 8})

        assert len(result) == 1
        assert result[0] == encode_vpu("add", 0, 4, 8)

    def test_tiled_matmul_instruction_count(self):
        """Test that 8x8 tiled matmul generates expected instruction count."""
        @kernel
        def tiled_8x8(W: Param, X: Param, Z: Param, temp: Param):
            from compiler.tpu_txt import matmul, add
            t2 = 16
            for i in range(2):
                for j in range(2):
                    Z_tile = Z + (i * 2 + j) * t2
                    for k in range(2):
                        X_tile = X + (i * 2 + k) * t2
                        W_tile = W + (j * 2 + k) * t2
                        if k == 0:
                            matmul(W_tile, X_tile, Z_tile)
                        else:
                            matmul(W_tile, X_tile, temp)
                            for elem in range(t2):
                                add(Z_tile + elem, temp + elem, Z_tile + elem)

        compiled = tiled_8x8.compile()

        # 4 output tiles, each needs:
        # - k=0: 1 matmul
        # - k=1: 1 matmul + 16 adds
        # Total per output tile: 1 + 1 + 16 = 18
        # Total: 4 * 18 = 72
        expected_count = 4 * (1 + 1 + 16)
        assert len(compiled.instructions) == expected_count


class TestPrebuiltKernels:
    """Tests for pre-built kernels."""

    def test_matmul_4x4_compiles(self):
        from compiler.kernels.matmul import matmul_4x4

        compiled = matmul_4x4.compile()
        assert compiled.name == "matmul_4x4"
        assert len(compiled.instructions) == 1

    def test_matmul_8x8_tiled_compiles(self):
        from compiler.kernels.matmul import matmul_8x8_tiled

        compiled = matmul_8x8_tiled.compile()
        assert compiled.name == "matmul_8x8_tiled"
        # 4 output tiles * (1 matmul + 1 matmul + 16 adds) = 72
        assert len(compiled.instructions) == 72

    def test_vector_add_compiles(self):
        from compiler.kernels.vpu import vector_add

        compiled = vector_add.compile()
        assert compiled.name == "vector_add"
        assert len(compiled.instructions) == 16  # Default n=16

    def test_vector_relu_compiles(self):
        from compiler.kernels.vpu import vector_relu

        compiled = vector_relu.compile()
        assert compiled.name == "vector_relu"
        assert len(compiled.instructions) == 16


class MockTpuDriver:
    """Mock TPU driver for testing without hardware."""

    def __init__(self):
        self.instructions = None
        self.compute_called = False

    def write_instructions(self, instructions):
        self.instructions = instructions

    def compute(self):
        self.compute_called = True


class TestKernelLauncher:
    """Tests for KernelLauncher."""

    def test_launch_single_kernel(self):
        """Test launching a single kernel."""
        from compiler.kernel import KernelLauncher
        from compiler.kernels.matmul import matmul_4x4
        from compiler.assembler import encode_halt

        mock_driver = MockTpuDriver()
        launcher = KernelLauncher(mock_driver)

        compiled = matmul_4x4.compile()
        launcher.launch(compiled, W=0, X=16, Z=32)

        assert mock_driver.compute_called
        assert len(mock_driver.instructions) == 2  # 1 matmul + 1 halt
        assert mock_driver.instructions[-1] == encode_halt()

    def test_launch_batch(self):
        """Test launching multiple kernels in a batch."""
        from compiler.kernel import KernelLauncher
        from compiler.kernels.matmul import matmul_4x4
        from compiler.kernels.vpu import vector_add
        from compiler.assembler import encode_halt

        mock_driver = MockTpuDriver()
        launcher = KernelLauncher(mock_driver)

        compiled_matmul = matmul_4x4.compile()
        compiled_vadd = vector_add.compile()

        batch = [
            (compiled_matmul, {'W': 0, 'X': 16, 'Z': 32}),
            (compiled_vadd, {'A': 48, 'B': 64, 'C': 80}),
        ]

        total = launcher.launch_batch(batch)

        assert mock_driver.compute_called
        # 1 matmul + 16 adds + 1 halt
        assert len(mock_driver.instructions) == 1 + 16 + 1
        assert total == 1 + 16  # Excludes halt
        assert mock_driver.instructions[-1] == encode_halt()

    def test_launch_batch_empty(self):
        """Test launching empty batch."""
        from compiler.kernel import KernelLauncher
        from compiler.assembler import encode_halt

        mock_driver = MockTpuDriver()
        launcher = KernelLauncher(mock_driver)

        total = launcher.launch_batch([])

        assert mock_driver.compute_called
        assert len(mock_driver.instructions) == 1  # Just halt
        assert total == 0


class TestEndToEnd:
    """End-to-end tests without hardware."""

    def test_matmul_full_resolution(self):
        """Test full compile + resolve flow for matmul."""
        from compiler.kernels.matmul import matmul_4x4

        compiled = matmul_4x4.compile()
        instructions = compiled.resolve({"W": 0, "X": 16, "Z": 32})

        # Should produce single matmul instruction
        assert len(instructions) == 1
        expected = encode_systolic(0, 16, 32, 16)  # m=4 -> length=16
        assert instructions[0] == expected

    def test_vector_add_full_resolution(self):
        """Test full compile + resolve flow for vector_add."""
        from compiler.kernels.vpu import vector_add

        compiled = vector_add.compile()
        instructions = compiled.resolve({"A": 0, "B": 100, "C": 200})

        assert len(instructions) == 16
        for i, instr in enumerate(instructions):
            expected = encode_vpu("add", i, 100 + i, 200 + i)
            assert instr == expected, f"Mismatch at index {i}"
