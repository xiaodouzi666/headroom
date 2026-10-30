# Lossless snapshot finalization performance repair

The R8 s1 candidate recorded 20 optimizer updates and 20 finite losses, but the host stopped it while finalizing `snapshot.json`. Its final artifact still says `capture_complete=false`, so the existing rejection remains correct. The saved checkpoint is `write:snapshot.json`; `snapshot.pickle` was complete. Parameter, precision and pairing fields are emitted after this serialization in `headroom/lab/hooks.py`, explaining why their final observations were missing. The model's next-round claim that the earlier patch checkpointed the whole model is also incorrect: the saved patch wraps each ResidualBlock.

The JSON writer already uses one `json.dumps` call without indentation for snapshots. The measured bottleneck is repeated typed-key construction in `encode_snapshot`, not token-at-a-time file writes. The saved capture has 202,808 stack references and 9,944,987 expanded frames, but only 397 native frame objects. The minimal change memoizes frame and stack objects within each encode call. Strong references and identity checks prevent ID reuse; memo counts are bounded by the existing table limits and fall back to value interning when full. Every reference still updates all existing expansion and depth checks. Input must remain stable during encoding, as documented; no cross-call cache exists.

| CPU measurement on the same saved capture | Original | Candidate |
|---|---:|---:|
| Encode seconds | 53.228972 | 2.594065 |
| JSON serialization seconds | 0.227437 | 0.227575 |
| Encoded bytes | 27,639,354 | 27,639,354 |

Encoding was 20.52 times faster in this one paired measurement, saving 50.63 seconds. Both encoded byte streams have SHA256 `8cf3ffbc845844d3e67434635f6df9e5a8f268741802a3da2aaf8503951b720d`; all codec statistics are identical. The candidate decoder also reproduced the native capture exactly, checked without exponential DAG expansion (1,354,659 unique comparisons). The complete candidate read/encode/serialize/decode/comparison took 16.253 seconds, with peak RSS 442,248 KiB. This is CPU replay of saved data, not a GPU repair rerun or a general benchmark distribution.

Input: `runs/final48-f3-retry/execution-r8-20261030/jobs/e5d4a541c34b49b09d2477efc1200348/lab/43834c0473d7494f86951152fd2c3a96/artifacts/snapshot.pickle`, 42,349,547 bytes, SHA256 `00d4a6000b5714b68f9ccb975bba39eb2b1e3f128fe774e6165aa9ab2f8477f7`. The original file was read only and never copied into this public report.

## Bounded reading and retained failures

All benchmark processes were restricted to 2 GiB address space, 75 CPU seconds, 90 wall seconds and 128 MiB maximum output file size, with socket/DNS use refused and nice 19. The initial product upload reader refused the capture at its 8-million-opcode limit (`inspect.log`). The report-only benchmark therefore uses the same primitive opcode allowlist and restricted Unpickler with count bounds tied to the at-most-50-MiB input (memo count at most 4 million); product upload limits were not changed.

`before.log` and `after.log` retain an initial comparison-harness failure: the 8-million-operation equality bound counted repeated references before deduplication. Their encoder/serialization measurements and identical output hashes were already complete. `benchmark-v3.py.txt` counts unique compared containers/scalars while preserving the bounded graph walk; `after-v3.log` records full equality success. The baseline SSH session detached, so its final exit code is not claimed. No source or historical evidence was modified to make these checks pass.

## Applied change and verification

Only `headroom/lab/snapshot_codec.py` and new `tests/test_snapshot_codec_memo.py` changed. The report candidate and applied codec are byte-identical. Existing codec tests plus seven new memo cases passed: **70 passed in 1.82 seconds**, under the parent/spawn closing guard. New cases cover exact shared/unshared envelope equality, no source mutation, cache-hit expansion limits, changed input across separate calls and full-cache fallback. Ruff, format and scoped diff checks passed. Independent read-only review by `frontend_browser_checks` found no blocking issue.

The 120-second Lab limit, complete-capture requirement, required snapshot JSON, all codec limits and numerical gates are unchanged. Nothing in this report upgrades the failed R8 run. A new authorized capture must independently finish finalization and pass the original verification requirements.
