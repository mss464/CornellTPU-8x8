"""
Mini-TPU Compiler Entry Point.

This CLI tool takes a kernel definition script (Python) and transforms it into 
a symbolic instruction trace. It is the primary way for developers to inspect 
the compiler's output before packaging.

Usage:
    python3 compiler/main.py [source_file.py] -o [output.txt]
"""

import sys
import os
import argparse
import importlib.util
from compiler.instructions import get_instruction_log, clear_instruction_log

def load_module_from_path(path: str):
    """Dynamically load and execute a Python file as a module."""
    module_name = os.path.basename(path).replace(".py", "")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

def main():
    parser = argparse.ArgumentParser(description="Mini-TPU Compiler CLI")
    parser.add_argument("source", help="Path to Python model file containing a build() entry point")
    parser.add_argument("-o", "--output", required=True, help="Destination for the symbolic trace")
    args = parser.parse_args()

    # Step 1: Initialize
    clear_instruction_log()

    # Step 2: Load User Code
    try:
        model = load_module_from_path(args.source)
    except Exception as e:
        print(f"Compilation Error (Load): {e}")
        sys.exit(1)

    # Step 3: Execute Tracing
    if not hasattr(model, "build"):
        print(f"Error: {args.source} must provide a 'build()' function.")
        sys.exit(1)

    try:
        model.build()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Step 4: Write Trace
    instructions = get_instruction_log()
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    
    with open(args.output, "w") as f:
        for instr in instructions:
            f.write(instr + "\n")
    
    print(f"Success! Trace saved to {args.output} ({len(instructions)} instructions)")

if __name__ == "__main__":
    main()
