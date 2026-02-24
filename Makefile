# Mini-TPU Project Makefile

.PHONY: help gpt2 gpt2-tpusim gpt2-tpu gemm setup gpt2-clean

help:
	@echo "Available targets:"
	@echo "  gpt2            : Run GPT-2 124M inference from demos/gpt2"
	@echo "  gpt2-tpusim     : Run GPT-2 124M with 32x32 systolic array simulation"
	@echo "  gpt2-tpu        : (TODO) Run the Transformer model offloaded to hardware TPU"
	@echo "  gemm            : Run Matrix Multiplication performance sweep (NumPy vs TPU Sim)"
	@echo "  board-test-rpc  : Test RPC remote execution connectivity (DEADBEEF test)"
	@echo "  setup           : Download GPT-2 weights and prepare environment"
	@echo "  gpt2-clean      : Remove GPT-2 weights and assets"
	@echo ""
	@echo "Options:"
	@echo "  DEBUG=1         : Enable TPU simulation debug (for gpt2 target)"
	@echo "  KERNEL_DEBUG=1  : Print kernel signatures and sizes (default: off)"
	@echo ""
	@echo "Environment Setup (for TPU Board Execution):"
	@echo "  export MINITPU_HOST=132.236.59.64  # Set your board IP"

# Optional debug flag: make gpt2 DEBUG=1
DEBUG ?= 0
KERNEL_DEBUG ?= 0

GPT2_DIR = demos/gpt2
GPT2_URL = https://huggingface.co/gpt2/resolve/main
FILES = pytorch_model.bin config.json vocab.json merges.txt

setup:
	@echo "Preparing GPT-2 weights and assets..."
	@mkdir -p $(GPT2_DIR)
	@for file in $(FILES); do \
		if [ ! -f $(GPT2_DIR)/$$file ] && [ ! -f $(GPT2_DIR)/gpt2_weights.npz ]; then \
			echo "Downloading $$file..."; \
			curl -L -o $(GPT2_DIR)/$$file $(GPT2_URL)/$$file; \
		fi; \
	done
	@if [ -f $(GPT2_DIR)/gpt2_weights.npz ]; then \
		echo "✅ GPT-2 weights already exist, skipping conversion."; \
	else \
		if tinytorch/.venv/bin/python3 -c "import torch" 2>/dev/null; then \
			echo "Torch found. Converting weights..."; \
			cd $(GPT2_DIR) && ../../tinytorch/.venv/bin/python3 ../tools/convert_weights.py; \
		else \
			echo "Torch not found. Downloading temporarily for weight conversion (this may take a few minutes)..."; \
			tinytorch/.venv/bin/python3 -m pip install torch --quiet; \
			cd $(GPT2_DIR) && ../../tinytorch/.venv/bin/python3 ../tools/convert_weights.py; \
			tinytorch/.venv/bin/python3 -m pip uninstall torch -y --quiet; \
		fi; \
	fi
	@rm -f $(GPT2_DIR)/pytorch_model.bin
	@echo "✅ Setup complete! weights and vocab ready in $(GPT2_DIR)/"

gpt2:
	export PYTHONPATH="$$(pwd)/tinytorch:$$PYTHONPATH" && \
	export MINI_TPU_DEBUG=0 && \
	export MINI_TPU_KERNEL_DEBUG=$(KERNEL_DEBUG) && \
	./tinytorch/.venv/bin/python3 "demos/gpt2/gpt2_benchmark.py"

gpt2-tpusim:
	export PYTHONPATH="$$(pwd)/tinytorch:$$PYTHONPATH" && \
	export MINI_TPU_DEBUG=1 && \
	export MINI_TPU_KERNEL_DEBUG=$(KERNEL_DEBUG) && \
	./tinytorch/.venv/bin/python3 "demos/gpt2/gpt2_benchmark.py"

gpt2-tpu:
	@echo "TODO: Implement hardware-accelerated MVP target"
	@exit 1

gemm:
	export PYTHONPATH="$$(pwd)/tinytorch:$$PYTHONPATH" && \
	./tinytorch/.venv/bin/python3 "demos/programs/gemm_sweep.py"

board-test-rpc:
	export PYTHONPATH="$$(pwd):$$PYTHONPATH" && \
	python3 "demos/programs/test_rpc.tu"

gpt2-clean:
	@echo "Cleaning GPT-2 weights and assets..."
	rm -f $(GPT2_DIR)/gpt2_weights.npz $(GPT2_DIR)/config.json $(GPT2_DIR)/vocab.json $(GPT2_DIR)/merges.txt
