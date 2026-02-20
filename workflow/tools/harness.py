#!/usr/bin/env python3
import sys
import argparse
import importlib.util
from pathlib import Path
import numpy as np
import json

# Setup path to import compiler and tools
# PROJECT_ROOT is mini-tpu/
# TOOLS_DIR is mini-tpu/workflow/tools/
TOOLS_DIR = Path(__file__).parent
PROJECT_ROOT = TOOLS_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from compiler.compile import Program
from compiler.executable import TPUExecutable

def to_tile_major(mat, tile_size=4):
    """Convert row-major matrix to tile-major layout."""
    rows, cols = mat.shape
    result = []
    for ti in range(rows // tile_size):
        for tj in range(cols // tile_size):
            tile = mat[ti*tile_size:(ti+1)*tile_size, tj*tile_size:(tj+1)*tile_size]
            result.extend(tile.flatten().tolist())
    return np.array(result, dtype=np.float32)

def save_executable(prog: Program, inputs: dict, outputs: dict, output_path: Path, verbose: bool = True):
    """Save program instructions and test data using TPUExecutable."""
    # Get memory map from program
    memory_map = {k: {"addr": v[0], "size": v[1]}
                  for k, v in prog.get_memory_map().items()}
    
    # Create executable object
    exe = TPUExecutable(
        instructions=prog.compile(),
        memory_map=memory_map,
        inputs=inputs,
        outputs=outputs
    )
    
    # Save
    exe.save(output_path, verbose=verbose)
    return output_path

def main():
    parser = argparse.ArgumentParser(description="Mini-TPU Program Harness")
    parser.add_argument("program_py", help="Path to the program definition script (.py)")
    parser.add_argument("-o", "--output", help="Output path for the generated executable (.npz)")
    args = parser.parse_args()

    program_path = Path(args.program_py).resolve()
    if not program_path.exists():
        print(f"Error: Program script not found: {program_path}")
        sys.exit(1)

    # Add program directory to path for relative imports if any
    if str(program_path.parent) not in sys.path:
        sys.path.insert(0, str(program_path.parent))

    # Import the program module
    spec = importlib.util.spec_from_file_location("program_module", program_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Check if the module has 'define_programs' or 'define_program'
    if hasattr(module, 'define_programs'):
        # Multi-executable script (like simd_pressure.py)
        # Returns a dict: {name: (prog, inputs, outputs)}
        programs = module.define_programs()
        for name, (prog, inputs, outputs) in programs.items():
            # If -o is provided, use it as a directory or base name
            if args.output:
                base_out = Path(args.output)
                if base_out.suffix == '.npz':
                    # If -o is a file, we append the name to it
                    out_path = base_out.parent / f"{base_out.stem}_{name}.npz"
                else:
                    out_path = base_out / f"{name}.npz"
            else:
                out_path = Path("workflow/binaries") / f"{name}.npz"
            
            save_executable(prog, inputs, outputs, out_path)
    elif hasattr(module, 'define_program'):
        # Single executable script
        prog, inputs, outputs = module.define_program()
        
        if args.output:
            out_path = Path(args.output)
            if out_path.suffix != '.npz':
                out_path = out_path / f"{program_path.stem}.npz"
        else:
            out_path = Path("workflow/binaries") / f"{program_path.stem}.npz"
            
        save_executable(prog, inputs, outputs, out_path)
    else:
        print(f"Error: Program script {program_path.name} must define 'define_program()' or 'define_programs()'")
        sys.exit(1)

if __name__ == "__main__":
    main()
