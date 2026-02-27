# Runtime Verification Makefile

PYTHON = python3
WORKSPACE_ROOT = ../..

.PHONY: all unit-test clean

all: unit-test

# 1. Unit testing of host-side execution and APIs
unit-test:
	@echo "Running Runtime unit tests (TUDA API, Allocator, etc)..."
	PYTHONPATH=$(WORKSPACE_ROOT) $(PYTHON) test_tuda.py

clean:
	rm -rf __pycache__
