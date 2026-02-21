
### Status
Current MVP: Offload TinyTorch Transformer's matmul operations to TPU.
- [ ] Debug the TPU hardware
    - [ ] Fix the Host interface
    - [ ] Verify the instruction memory capacity
        - [ ] Implement branch/loop/complex instructions
    - [ ] Verify the data memory capacity
    - [ ] Implement address generation (preferrably with just scalar operations)
- [ ] Create TPU program equivalent to @systolic_tiled_matmul.py