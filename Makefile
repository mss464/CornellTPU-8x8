# Mini-TPU Project Makefile

.PHONY: help mvp-sw mvp-hw

help:
	@echo "Available targets:"
	@echo "  mvp-sw  : Run the Transformer model with the software-simulated tiled GEMM"
	@echo "  mvp-hw  : (TODO) Run the Transformer model offloaded to hardware TPU"

mvp-sw:
	export PYTHONPATH="$$(pwd)/tinytorch:$$PYTHONPATH" && ./.venv/bin/python3 "tinytorch/src/13_transformers/13_transformers.py"

mvp-hw:
	@echo "TODO: Implement hardware-accelerated MVP target"
	@exit 1
