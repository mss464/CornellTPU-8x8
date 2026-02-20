"""
Mini-TPU Executable Format (.npz).

This module defines the binary distribution format for Mini-TPU programs.
A TPUExecutable is a self-contained unit that bundles:
1. Compiled instruction stream
2. Static memory layout (addresses and sizes)
3. Reference test data (inputs and expected outputs)
4. Optional developer metadata

Example:
    # Save an executable
    exe = TPUExecutable(instructions, memory_map, inputs, outputs)
    exe.save("program.npz")

    # Load and inspect
    exe = TPUExecutable.load("program.npz")
    print(f"Loaded {len(exe.instructions)} instructions")
"""

from dataclasses import dataclass
import json
import numpy as np
from typing import Dict, Any, Union, List
from pathlib import Path


@dataclass
class TPUExecutable:
    """
    A persistent TPU program archive.
    
    Fields:
        instructions: 64-bit hardware instruction words.
        memory_map: mapping of buffer names to {addr, size}.
        inputs: Input data arrays to be loaded into TPU memory.
        outputs: Expected result arrays for hardware verification.
        metadata: Arbitrary info (date, git hash, etc).
    """
    instructions: np.ndarray
    memory_map: Dict[str, Dict[str, int]]
    inputs: Dict[str, np.ndarray]
    outputs: Dict[str, np.ndarray]
    metadata: Dict[str, Any] = None

    def save(self, path: Union[str, Path], verbose: bool = False):
        """Serialize the executable to a compressed .npz archive."""
        path = Path(path)
        path.parent.mkdir(exist_ok=True, parents=True)

        # We encode metadata as JSON within the NumPy archive
        save_dict = {
            'instructions': self.instructions.astype(np.uint64),
            'memory_map': json.dumps(self.memory_map),
            'manifest': json.dumps({
                'inputs': list(self.inputs.keys()),
                'outputs': list(self.outputs.keys()),
                'metadata': self.metadata or {}
            })
        }

        # Prefix data arrays to prevent namespace collisions
        for k, v in self.inputs.items():
            save_dict[f"in_{k}"] = v
        for k, v in self.outputs.items():
            save_dict[f"out_{k}"] = v

        np.savez(path, **save_dict)
        
        if verbose:
            print(f"Serialized TPU executable to: {path.name}")
            print(f"  Size: {len(self.instructions)} words")

    @classmethod
    def load(cls, path: Union[str, Path]) -> "TPUExecutable":
        """Deserialize a TPUExecutable from a .npz file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Executable not found: {path}")
            
        data = np.load(path, allow_pickle=True)

        if 'instructions' not in data or 'memory_map' not in data:
            raise ValueError(f"File {path} is not a valid Mini-TPU executable.")

        instructions = data['instructions']
        memory_map = json.loads(str(data['memory_map']))
        
        inputs = {}
        outputs = {}
        metadata = {}

        if 'manifest' in data:
            manifest = json.loads(str(data['manifest']))
            inputs = {k: data[f"in_{k}"] for k in manifest.get('inputs', [])}
            outputs = {k: data[f"out_{k}"] for k in manifest.get('outputs', [])}
            metadata = manifest.get('metadata', {})
        else:
            # Fallback for older formats
            if 'inputs' in data: inputs = data['inputs'].item()
            if 'outputs' in data: outputs = data['outputs'].item()

        return cls(
            instructions=instructions,
            memory_map=memory_map,
            inputs=inputs,
            outputs=outputs,
            metadata=metadata
        )
