# Mini-TPU Project Makefile

.PHONY: help gpt2 gpt2-tpusim gpt2-tpu gemm setup

help:
	@echo "Available targets:"
	@echo "  gpt2            : Run GPT-2 124M inference from workflow/gpt2"
	@echo "  gpt2-tpusim     : Run GPT-2 124M with 32x32 systolic array simulation"
	@echo "  gpt2-tpu        : (TODO) Run the Transformer model offloaded to hardware TPU"
	@echo "  gemm            : Run Matrix Multiplication performance sweep (NumPy vs TPU Sim)"
	@echo "  setup           : Download GPT-2 weights and prepare environment"

# Optional debug flag: make gpt2 DEBUG=1
DEBUG ?= 0

setup:
	@echo "Preparing GPT-2 weights and assets..."
	@mkdir -p workflow/gpt2
	@curl -L -o workflow/gpt2/pytorch_model.bin https://huggingface.co/gpt2/resolve/main/pytorch_model.bin
	@curl -L -o workflow/gpt2/config.json https://huggingface.co/gpt2/resolve/main/config.json
	@curl -L -o workflow/gpt2/vocab.json https://huggingface.co/gpt2/resolve/main/vocab.json
	@curl -L -o workflow/gpt2/merges.txt https://huggingface.co/gpt2/resolve/main/merges.txt
	@echo "Converting weights to .npz format (requires torch)..."
	@cd workflow/gpt2 && ../../tinytorch/.venv/bin/python3 -m pip install torch --quiet
	@cd workflow/gpt2 && ../../tinytorch/.venv/bin/python3 convert_weights.py
	@rm workflow/gpt2/pytorch_model.bin workflow/gpt2/convert_weights.py
	@echo "✅ Setup complete! weights and vocab ready in workflow/gpt2/"

gpt2:
	export PYTHONPATH="$$(pwd)/tinytorch:$$PYTHONPATH" && \
	export MINI_TPU_DEBUG=0 && \
	./tinytorch/.venv/bin/python3 "workflow/gpt2/gpt2_benchmark.py"

gpt2-tpusim:
	export PYTHONPATH="$$(pwd)/tinytorch:$$PYTHONPATH" && \
	export MINI_TPU_DEBUG=1 && \
	./tinytorch/.venv/bin/python3 "workflow/gpt2/gpt2_benchmark.py"

gpt2-tpu:
	@echo "TODO: Implement hardware-accelerated MVP target"
	@exit 1

gemm:
	export PYTHONPATH="$$(pwd)/tinytorch:$$PYTHONPATH" && \
	./tinytorch/.venv/bin/python3 "workflow/gemm_sweep.py"
