# Accumulated loss retains graphs

Run: b7f348d0dc8d423f8076b81fd2c15375
Outcome: Historical target met

A tensor accumulator kept computation graphs alive across training updates.

Peak before: 24768717824 bytes
Peak after: 2533996544 bytes
Loss comparison: identical; 5 scalars
First five backward-loss scalars compared with an original-workload saved-tensor offload reference; the candidate completed 20 optimizer updates.
Parameters: 50374656 → 50374656
Candidate optimizer updates: 20

## Limitations
- Numerical comparison covers five backward-loss scalars against an offloaded reference, not all 20 candidate updates.
- No Tavily source links were recorded for this run.
