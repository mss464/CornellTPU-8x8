import sys
import os
import numpy as np
import importlib.util
from pathlib import Path

# Add project roots to path
project_root = Path("/work/shared/users/phd/sk3463/projects/mini-tpu/tinytorch").resolve()
sys.path.insert(0, str(project_root))

# Helper to import numeric modules
def import_numeric_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

target_file = project_root / "src/13_transformers/13_transformers.py"
transformers_mod = import_numeric_module(str(target_file), "transformers_src")

class DetailedTracer:
    def __init__(self, include_libs):
        self.include_libs = include_libs
        self.calls = []
        self.stack = []
        self.indent_level = 0

    def get_module_category(self, filename, func_name):
        if 'numpy' in filename or 'numpy' in func_name:
            return "NumPy"
        if 'tinytorch' in filename or 'transformers_src' in filename:
            return "TinyTorch"
        return "Other"

    def trace_callback(self, frame, event, arg):
        if event != 'call':
            return self.trace_callback
            
        filename = frame.f_code.co_filename
        func_name = frame.f_code.co_name
        module_name = frame.f_globals.get('__name__', '')
        
        # We want to see TinyTorch calls and their transitions to NumPy
        is_tinytorch = 'tinytorch' in filename or 'transformers_src' in module_name
        is_numpy = 'numpy' in filename or ('numpy' in module_name) or (hasattr(arg, '__name__') and 'numpy' in arg.__name__)

        if is_tinytorch or is_numpy:
            category = self.get_module_category(filename, func_name)
            
            # Extract shape information if possible
            shapes = []
            for arg_name, value in frame.f_locals.items():
                if isinstance(value, (np.ndarray, np.generic)):
                    shapes.append(f"{arg_name}: {value.shape}")
                elif hasattr(value, 'data') and isinstance(value.data, np.ndarray):
                    # For tinytorch.Tensor
                    shapes.append(f"{arg_name}(T): {value.data.shape}")

            shape_str = f" [{', '.join(shapes)}]" if shapes else ""
            
            # Simple display path
            short_file = filename.split('/')[-1] if '/' in filename else filename
            
            call_info = {
                'cat': category,
                'func': func_name,
                'file': short_file,
                'level': self.indent_level,
                'shapes': shape_str
            }
            self.calls.append(call_info)
            
            # Print in real-time for comprehensive feel
            indent = "  " * self.indent_level
            icon = "🧱" if category == "TinyTorch" else "🔢"
            print(f"{indent}{icon} {category}: {func_name} ({short_file}){shape_str}")
            
            self.indent_level += 1
            return self.trace_inner
        return None

    def trace_inner(self, frame, event, arg):
        if event == 'return':
            self.indent_level -= 1
        return None

def run_comprehensive_trace():
    tracer = DetailedTracer(include_libs=['tinytorch', 'numpy', 'transformers_src'])
    
    # Run a representative subset of the transformation
    # We'll use a small TransformerBlock forward pass
    print("🚀 INITIALIZING TRANSFORMER COMPONENTS...")
    embed_dim = 32
    num_heads = 2
    block = transformers_mod.TransformerBlock(embed_dim=embed_dim, num_heads=num_heads)
    x = transformers_mod.Tensor(np.random.randn(1, 4, embed_dim))
    
    print("\n🔥 STARTING COMPREHENSIVE TRACE (FORWARD PASS) 🔥")
    print("-" * 60)
    
    sys.settrace(tracer.trace_callback)
    try:
        # This will trigger the full chain down to NumPy
        output = block.forward(x)
    finally:
        sys.settrace(None)
        
    print("-" * 60)
    print(f"✅ TRACE COMPLETE. CAPTURED {len(tracer.calls)} CALLS.")
    
    # Generate Mermaid for Visualization
    with open("transformer_trace.mmd", "w") as f:
        f.write("graph TD\n")
        for i in range(len(tracer.calls) - 1):
            curr = tracer.calls[i]
            # Find next call at level + 1
            for j in range(i + 1, len(tracer.calls)):
                next_call = tracer.calls[j]
                if next_call['level'] == curr['level'] + 1:
                    # Link them
                    c_id = f"c{i}"
                    n_id = f"c{j}"
                    c_label = f"{curr['cat']}: {curr['func']}"
                    n_label = f"{next_call['cat']}: {next_call['func']}"
                    f.write(f'  {c_id}["{c_label}"] --> {n_id}["{n_label}"]\n')
                elif next_call['level'] <= curr['level']:
                    break

if __name__ == "__main__":
    run_comprehensive_trace()
