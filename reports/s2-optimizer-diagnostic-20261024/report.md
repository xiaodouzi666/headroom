# Stable s2 single-tensor AdamW diagnostic repeat

**Diagnostic checks passed. This is not original T1.2 acceptance and not a model-generated repair.**
The canonical scenario and previous failed/runtime-changed evidence are unchanged.

The sole GPU execution used the exact previously reviewed candidate:
only the AdamW constructor changes foreach=True to foreach=False.
Candidate SHA-256: 1374cb6b6db4056f3c0334f7151b4fd506e4ef5e64536669ae7ba968c7e20a3d.
Original SHA-256: bb1d12c69ce5525e6eab67e709740cb2d578c070afa8b094b5f4b6906648bc5b.
Wrapper seed 1337, script args --seed 1337, full model (no tiny mode),
20 optimizer updates, max_seconds=180. The candidate ran only through the
network-disabled Docker Lab. No provider API call or production-source edit occurred.

A diagnostic-harness provenance assertion failed before any GPU call because
its first-match replacement selected a comment. The assertion was corrected
to match the full AdamW constructor line. preflight-failure.json retains this
failure; the candidate bytes did not change. There was exactly one target GPU run.

## Stable execution and evidence

- Run: /home/xiaodouzi/workspace/headroom/runs/scenario-design/s2-single-adamw-stable-20261024T120037Z/lab/615d83f6455e44a58c3e5a420c9c863a
- Captured updates: 20; capture complete: true.
- Cleanup verified: true; GPU before/after compute-process lists empty.
- Lab shared_gpu=false and gpu_observation_complete=true. These samples do not
  establish continuous exclusivity.
- Every regular non-bytecode headroom source file, including untracked modules,
  was hashed before imports and after capture/evidence generation: 56 files,
  runtime_unchanged=true, changed_files=[].
- Complete allocator history: 60549 events; unknown events: 0.
- Replayed peak equals native counter; terminal replay matches capture;
  all peak bytes are covered by the composition.
- Canonical source, historical result/evidence and prior experiment/report/result
  hashes all remain identical. The previous runtime_changed failure is preserved.

## Measurements

| Quantity | Historical foreach baseline | Stable single-tensor candidate |
|---|---:|---:|
| Peak allocated bytes | 21553250816 | 17390699008 |
| Optimizer state bytes at peak | 8593604608 | 8593604608 |
| State / peak | 39.8715009692% | 49.4149464840% |
| Updates | 20 | 20 |

Runtime parameter count is 1,074,200,576, with complete Lab coverage.
Maximum absolute difference across the 20 historical/candidate losses is
2.38418579102e-07, below the unchanged FP32 1e-3 bound.
The historical run lacks this newer runtime parameter-count observation; none
was backfilled.

The optimizer moments remain two allocations of 4,296,802,304 bytes each,
from AdamW _init_group lines 148 and 152. The candidate's actual peak shows
67,141,632-byte and 67,108,864-byte temporary allocations at
_single_tensor_adamw line 427. Optimizer-state classification is unchanged;
no temporary allocation was relabeled. The prior report preserves the historical
foreach P-sized temporary mechanism and original 39.8715% failed threshold.

Observed peak reduction versus the historical capture is
19.312872%. Historical and current Lab versions differ.
The new step median is 180.666218 ms and outer call wall time is
26.779066 s; concurrent CPU regressions may affect these.
**No speedup or throughput acceptance is claimed.**

## Decision boundary

This stable result supports review of a single-tensor AdamW scenario mode while
retaining the original foreach reproduction. It does not apply that change,
change the >=40% requirement, close original T1.2, or resolve the separate
already-fit:22GB / at-least-two-round repair issue. User review of the original
scenario/acceptance conflict remains separate.

Artifacts: receipt.json, preflight-failure.json, run_experiment.py,
candidate.diff, candidate-source/train.py, original-train.py,
evidence/evidence.json, evidence/evidence.md, evidence/timeline.png.
The previous record remains at /home/xiaodouzi/workspace/headroom/runs/scenario-design/s2-single-adamw-20261024T114329Z-35547beb.

## Joint threshold constraint

For the current unchanged 1,074,200,576 parameters, the two fp32 AdamW
moment tensors total 8,593,604,608 bytes. Requiring those tensors to be
at least 40% of baseline peak implies a peak of at most
21.484011520 GB, which already fits the separate 22 GB target.
Thus changing foreach alone cannot simultaneously make this current-size fixture
meet the 40% baseline gate and require a capacity repair to reach 22 GB.

This is a constraint on the current fixture, not a reason to lower either original
threshold. A future separately versioned fixture calibration would need to satisfy
both constraints before model repair evaluation, and retain all existing baseline
results. The separate default-policy versus bf16 Pareto requirement also remains
unresolved; this experiment does not change numerical permissions.
