# Compiler Verification Makefile

PYTHON = python3
SMOKE_TEST = test_workflow.py
ISA_TEST = test_isa.py
MLP_KERNEL = ../kernels/mlp.py
WORKSPACE_ROOT = ../..

.PHONY: all smoke-test isa-test cli-test clean

all: smoke-test isa-test cli-test

# 1. Pipeline Smoke Test
smoke-test:
	@echo "Running Pipeline Smoke Test..."
	PYTHONPATH=$(WORKSPACE_ROOT) $(PYTHON) $(SMOKE_TEST)

# 2. ISA/Codegen Test
isa-test:
	@echo "Running ISA/Codegen tests..."
	PYTHONPATH=$(WORKSPACE_ROOT) $(PYTHON) $(ISA_TEST)

# 2. CLI Integration Test
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
