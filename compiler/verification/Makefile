# Compiler Verification Makefile

PYTHON = python3
PYTEST = pytest
SMOKE_TEST = test_workflow.py
DEVICE_TEST = test_device_binary.py
ISA_TEST = test_isa.py
KERNEL_TEST = test_kernel.py
MLP_KERNEL = ../../demos/kernels/mlp.py
WORKSPACE_ROOT = ../..

.PHONY: all smoke-test device-test isa-test kernel-test cli-test clean

all: smoke-test device-test isa-test kernel-test cli-test

# 1. Pipeline Smoke Test
smoke-test:
	@echo "Running Pipeline Smoke Test..."
	PYTHONPATH=$(WORKSPACE_ROOT) $(PYTHON) $(SMOKE_TEST)

# 2. Pure Device Binary Test
device-test:
	@echo "Running Pure Device Binary Test..."
	PYTHONPATH=$(WORKSPACE_ROOT) $(PYTHON) $(DEVICE_TEST)

# 3. ISA/Codegen Test
isa-test:
	@echo "Running ISA/Codegen tests..."
	PYTHONPATH=$(WORKSPACE_ROOT) $(PYTHON) $(ISA_TEST)

# 4. Kernel AST and Python Resolution Test
kernel-test:
	@echo "Running Kernel Object Tests via Pytest..."
	PYTHONPATH=$(WORKSPACE_ROOT) $(PYTEST) $(KERNEL_TEST) -v

# 5. CLI Integration Test
cli-test:
	@echo "Running CLI Trace Test (MLP)..."
	PYTHONPATH=$(WORKSPACE_ROOT) $(PYTHON) ../main.py $(MLP_KERNEL) -o /tmp/mlp_trace.txt
	@if [ -f /tmp/mlp_trace.txt ]; then \
		echo "Success: Trace generated with $$(wc -l < /tmp/mlp_trace.txt) instructions"; \
		rm /tmp/mlp_trace.txt; \
	else \
		echo "Failure: Trace file not found"; \
		exit 1; \
	fi

clean:
	rm -f *.npz
