
### Status
Current MVP: Offload TinyTorch Transformer's matmul operations to TPU.
- [ ] Debug the TPU hardware
    - [ ] Fix the Host interface
    - [ ] Verify the instruction memory capacity
        - [ ] Implement branch/loop/complex instructions
    - [ ] Verify the data memory capacity
    - [ ] Implement address generation (preferrably with just scalar operations)
- [ ] Create TPU program equivalent to @systolic_tiled_matmul.py

---

### 🛠️ Developer Notes for AI Agents
- **Path Handling**: Always use **absolute paths** when calling tools. The environment is sensitive to `cwd` mismatches.
- **Workflow Speed**: For heavy simulations like `systolic_tiled_matmul.py`, use the highest possible `TILE_DIM` (e.g., 16 or 32) and offload the inner block math to NumPy to avoid Python loop overhead.
- **Resource Limits**: When using `read_url_content`, non-binary text formats are preferred. Pretrained weights should be converted to `.npz` locally rather than downloaded directly if possible.