import os
import sys
import time
import numpy as np
import json
from pathlib import Path

# Add project root to path so we can import tinytorch
# Script is in workflow/gpt2/
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent.parent.absolute()
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

import argparse

# Parse arguments first before imports that might check env vars
parser = argparse.ArgumentParser(description="GPT-2 124M Inference Benchmark")
parser.add_argument("--kernel-debug", action="store_true", help="Print each kernel with sizes")
args, unknown = parser.parse_known_args()

if args.kernel_debug:
    os.environ["MINI_TPU_KERNEL_DEBUG"] = "1"

from tinytorch import Tensor, GPT, CharTokenizer, AdamW, CrossEntropyLoss
from tinytorch.core.tokenization import BPETokenizer

# ANSI Color Codes
BLUE = "\033[94m"
CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
RESET = "\033[0m"

def get_gpt2_124m_config():
    return {
        "vocab_size": 50257,
        "n_layer": 12,
        "n_head": 12,
        "n_embd": 768,
        "max_seq_len": 1024
    }

def setup_model(config, weights_path=None):
    if weights_path is None:
        weights_path = str(script_dir / "gpt2_weights.npz")
        
    print(f"Initializing GPT-2 124M model...")
    model = GPT(
        vocab_size=config["vocab_size"],
        embed_dim=config["n_embd"],
        num_layers=config["n_layer"],
        num_heads=config["n_head"],
        max_seq_len=config["max_seq_len"]
    )
    
    if os.path.exists(weights_path):
        print(f"Loading weights from {weights_path}...")
        weights = np.load(weights_path)
        
        # Determine if weights labels have transformer. prefix
        has_prefix = 'transformer.wte.weight' in weights
        prefix_str = "transformer." if has_prefix else ""
        print(f"  Detecting weight format: {'With' if has_prefix else 'Without'} 'transformer.' prefix")

        # Helper to set parameter data
        def set_param(param, key):
            full_key = prefix_str + key
            if full_key not in weights:
                # Try the other way if it fails
                alt_key = key if has_prefix else "transformer." + key
                if alt_key in weights:
                    full_key = alt_key
                else:
                    print(f"  ❌ Key not found: {full_key} (tried {alt_key} too)")
                    return

            data = weights[full_key]
            if param.data.shape != data.shape:
                # Handle GPT-2 specific Transpose for Conv1D layers (attn.c_attn, attn.c_proj, mlp.c_fc, mlp.c_proj)
                if param.data.shape == data.T.shape:
                    data = data.T
                else:
                    print(f"  ⚠️ Shape mismatch for {full_key}: {param.data.shape} != {data.shape}")
                    return
            param.data = data.copy()

        try:
            # 1. Embeddings
            set_param(model.embedding_layer.token_embedding.weight, 'wte.weight')
            set_param(model.embedding_layer.pos_encoding.position_embeddings, 'wpe.weight')
            
            # 2. Blocks
            for i in range(config["n_layer"]):
                block = model.blocks[i]
                h_prefix = f'h.{i}.'
                
                # LayerNorms
                set_param(block.ln1.gamma, f'{h_prefix}ln_1.weight')
                set_param(block.ln1.beta, f'{h_prefix}ln_1.bias')
                set_param(block.ln2.gamma, f'{h_prefix}ln_2.weight')
                set_param(block.ln2.beta, f'{h_prefix}ln_2.bias')
                
                # Attention - c_attn is (embed_dim, 3*embed_dim)
                c_attn_w_key = f'{h_prefix}attn.c_attn.weight'
                c_attn_b_key = f'{h_prefix}attn.c_attn.bias'
                
                if prefix_str + c_attn_w_key in weights or (not has_prefix and c_attn_w_key in weights):
                    w_key = prefix_str + c_attn_w_key if prefix_str + c_attn_w_key in weights else c_attn_w_key
                    b_key = prefix_str + c_attn_b_key if prefix_str + c_attn_b_key in weights else c_attn_b_key
                    
                    c_attn_w = weights[w_key]
                    if c_attn_w.shape != (config["n_embd"], 3 * config["n_embd"]):
                        c_attn_w = c_attn_w.T # Transpose if (3*E, E)
                    
                    c_attn_b = weights[b_key]
                    
                    # Split into Q, K, V
                    q_w, k_w, v_w = np.split(c_attn_w, 3, axis=1)
                    q_b, k_b, v_b = np.split(c_attn_b, 3)
                    
                    block.attention.q_proj.weight.data = q_w.copy()
                    block.attention.q_proj.bias.data = q_b.copy()
                    block.attention.k_proj.weight.data = k_w.copy()
                    block.attention.k_proj.bias.data = k_b.copy()
                    block.attention.v_proj.weight.data = v_w.copy()
                    block.attention.v_proj.bias.data = v_b.copy()
                
                # Attention Output
                set_param(block.attention.out_proj.weight, f'{h_prefix}attn.c_proj.weight')
                set_param(block.attention.out_proj.bias, f'{h_prefix}attn.c_proj.bias')
                
                # MLP
                set_param(block.mlp.linear1.weight, f'{h_prefix}mlp.c_fc.weight')
                set_param(block.mlp.linear1.bias, f'{h_prefix}mlp.c_fc.bias')
                set_param(block.mlp.linear2.weight, f'{h_prefix}mlp.c_proj.weight')
                set_param(block.mlp.linear2.bias, f'{h_prefix}mlp.c_proj.bias')
            
            # 3. Final LN and Head
            set_param(model.ln_f.gamma, 'ln_f.weight')
            set_param(model.ln_f.beta, 'ln_f.bias')
            
            # Check for lm_head
            lm_head_key = 'lm_head.weight'
            if lm_head_key in weights or 'transformer.' + lm_head_key in weights:
                set_param(model.lm_head.weight, lm_head_key)
            else:
                set_param(model.lm_head.weight, 'wte.weight')
                
            print("✅ Weights loaded and mapped successfully.")
        except Exception as e:
            print(f"❌ Error mapping weights: {e}")
    else:
        print(f"💡 No weights found at {weights_path}. Running with random initialization.")
        
    return model

def main():
    config = get_gpt2_124m_config()
    
    # Check for manual overrides
    mode = os.environ.get("BENCHMARK_MODE", "full")
    if mode == "lite":
        print(f"{YELLOW}Running in LITE mode (3 layers, 384 dim) for speed{RESET}")
        config["n_layer"] = 3
        config["n_embd"] = 384
        config["n_head"] = 6
    else:
        print(f"{CYAN}Running FULL GPT-2 124M (12 layers, 768 dim, 12 heads){RESET}")
    
    use_tpu_sim = os.environ.get("MINI_TPU_DEBUG") == "1"
    
    print("="*60)
    print(f"{BOLD}GPT-2 124M REAL-WORLD BENCHMARK{RESET}")
    print("="*60)
    print(f"{YELLOW}Backend:{RESET} TinyTorch + NumPy")
    
    if use_tpu_sim:
        print(f"{YELLOW}Compute:{RESET} {MAGENTA}32x32 Systolic Array Simulation (PURE PYTHON){RESET}")
    else:
        print(f"{YELLOW}Compute:{RESET} {GREEN}Raw CPU (NumPy Optimized BLAS){RESET}")
    
    print(f"Model: {config['n_layer']} layers, {config['n_embd']} dim, {config['n_head']} heads")
    print("-" * 60)

    # Initialize tokenizer
    tokenizer_found = False
    vocab_path = str(script_dir / "vocab.json")
    merges_path = str(script_dir / "merges.txt")

    if os.path.exists(vocab_path):
        try:
            from tinytorch.core.tokenization import BPETokenizer
            tokenizer = BPETokenizer()
            
            print(f"{GREEN}✅ Loading GPT-2 BPE vocabulary from vocab.json...{RESET}")
            with open(vocab_path, "r", encoding="utf-8") as f:
                vocab_data = json.load(f)
            
            tokenizer.token_to_id = vocab_data
            tokenizer.id_to_token = {int(v): k for k, v in vocab_data.items()}
            tokenizer.vocab = [tokenizer.id_to_token[i] for i in range(len(tokenizer.id_to_token))]
            tokenizer.vocab_size = len(vocab_data)
            
            def gpt2_encode(text):
                processed_text = text.replace(" ", "Ġ")
                if not processed_text.startswith("Ġ") and text.startswith(" "):
                    processed_text = "Ġ" + processed_text
                word_tokens = tokenizer._apply_merges(list(processed_text))
                tokens = [tokenizer.token_to_id.get(t, 0) for t in word_tokens]
                return tokens

            def gpt2_decode(tokens):
                raw_text = "".join([tokenizer.id_to_token.get(t, "") for t in tokens])
                return raw_text.replace('Ġ', ' ').replace('Ċ', '\n')
            
            tokenizer.encode = gpt2_encode
            tokenizer.decode = gpt2_decode
            
            if os.path.exists(merges_path):
                print(f"{GREEN}✅ Loading BPE merges from merges.txt...{RESET}")
                with open(merges_path, "r", encoding="utf-8") as f:
                    merges_data = f.read().split('\n')[1:-1]
                    tokenizer.merges = [tuple(m.split()) for m in merges_data]
            
            tokenizer_found = True
            print(f"{GREEN}✅ Tokenizer ready (Vocab size: {tokenizer.vocab_size}){RESET}")
        except Exception as e:
            print(f"{YELLOW}⚠️  Could not load GPT-2 vocab: {e}{RESET}")

    if not tokenizer_found:
        tokenizer = CharTokenizer()
        tokenizer.build_vocab(["The future of AI is built from first principles."])
    
    model = setup_model(config)
    
    print(f"\n{BOLD}{MAGENTA}--- GPT-2 Interactive Inference ---{RESET}")
    user_prompt = input(f"{YELLOW}Enter prompt (or press Enter for default): {RESET}")
    prompt = user_prompt if user_prompt.strip() else "The future of AI is"
    
    print(f"\n{CYAN}Using prompt: '{prompt}'{RESET}")
    prompt_tokens = tokenizer.encode(prompt)
    if not prompt_tokens: prompt_tokens = [1, 2, 3]
    
    user_num_tokens = input(f"{YELLOW}How many tokens to generate? (default 5): {RESET}")
    try:
        num_tokens = int(user_num_tokens) if user_num_tokens.strip() else 5
    except ValueError:
        num_tokens = 5
    
    input_tensor = Tensor(np.array([prompt_tokens]))
    
    print(f"{YELLOW}Warmup (Forward Pass)...{RESET}")
    _ = model.forward(input_tensor)
    
    print(f"{GREEN}Generating {num_tokens} tokens...{RESET}")
    start_time = time.time()
    generated_tensor = model.generate(input_tensor, max_new_tokens=num_tokens, temperature=1.0)
    total_time = time.time() - start_time
    
    generated_ids = generated_tensor.data[0].tolist()
    output_text = tokenizer.decode(generated_ids)
    
    print("\n" + "="*60)
    print(f"{BOLD}GENERATED OUTPUT:{RESET}")
    print(f"'{output_text}'")
    print("="*60)
    
    print(f"\n{BLUE}Performance Stats:{RESET}")
    print(f"  Total Time: {total_time:.2f}s")
    print(f"  Throughput: {num_tokens / total_time:.2f} tokens/sec")
    print(f"  Latency: {(total_time/num_tokens)*1000:.2f}ms/token")

if __name__ == "__main__":
    main()
