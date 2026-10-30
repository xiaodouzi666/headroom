# An unused teacher model on the GPU

Run: d10adf0ffac74dcf8d874a460a2a3628
Outcome: Historical target met

The patch kept the unused teacher on the CPU while preserving the recorded parameter count.

Peak before: 3100141568 bytes
Peak after: 121791488 bytes
Loss comparison: identical; 20 scalars
The recorded full backward-loss series was compared.
Parameters: 747474432 → 747474432
Candidate optimizer updates: 20

## Limitations
- The historical loss comparison is recorded, but runtime pairing checks for inputs, effective batch and objective were not established.
- No Tavily source links were recorded for this run.
