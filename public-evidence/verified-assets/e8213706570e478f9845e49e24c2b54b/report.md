# Accumulated loss retains graphs

Run: e8213706570e478f9845e49e24c2b54b
Outcome: Historical target met

The recorded evaluation removed a tensor accumulator that retained computation graphs across updates.

Peak before: 24768717824 bytes
Peak after: 2533996544 bytes
Loss comparison: identical; 5 scalars
First five backward-loss scalars compared with an original-workload saved-tensor offload reference; the candidate completed 20 optimizer updates.
Parameters: 50374656 → 50374656
Candidate optimizer updates: 20

## Limitations
- Numerical comparison covers five backward-loss scalars against an offloaded reference, not all 20 candidate updates.
- No Tavily source links were recorded for this run.
