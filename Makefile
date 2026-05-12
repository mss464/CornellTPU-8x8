# Makefile - Mini-TPU Memory Subsystem

VIVADO := vivado -mode batch -source

.PHONY: all ip bitstream clean test

all: ip bitstream

# Package the RTL as a Xilinx IP
ip:
	$(VIVADO) scripts/package_ip.tcl

# Build the block design and bitstream
bitstream:
	$(VIVADO) scripts/build_bitstream.tcl

# Clean build artifacts
clean:
	rm -rf build/ vivado*.log vivado*.jou vivado*.backup.log
	rm -rf ultra96-v2/output/

# Run board-level tests (requires SSH connection to board)
# Usage: make test BOARD_IP=132.236.59.68
test:
	python3 tests/test_mem_system.py --bitstream build/minitpu.bit --program
