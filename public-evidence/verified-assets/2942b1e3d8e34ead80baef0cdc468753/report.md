# AdamW training above the memory target

Run: 2942b1e3d8e34ead80baef0cdc468753
Outcome: Historical target met

Disabling foreach optimizer updates and adding activation checkpointing reduced the recorded peak below 22 GB.

Peak before: 22919430656 bytes
Peak after: 18639258624 bytes
Loss comparison: within_tol; 20 scalars
The recorded full backward-loss series was compared.
Parameters: 1141338112 → 1141338112
Candidate optimizer updates: 20

## Limitations
- This is the historical fp32 result with tolerance-based comparison, not a bit-identical strict result or a bf16 trade-off run.
- The historical loss comparison is recorded, but runtime pairing checks for inputs, effective batch and objective were not established.
- Losses matched within tolerance; they were not bit-identical.
- Retrieved documentation was not matched to the installed PyTorch version.
