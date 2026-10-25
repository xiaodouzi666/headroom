# Explicit baseline-derived checkpoint reference, 2026-10-25

The new opt-in strategy is original_workload_checkpoint. It is a **baseline-derived transformed reference**, not byte-for-byte execution of the original source. The legacy strategy and saved-tensor-offload strategy remain separate. No old baseline, scenario source, numerical tolerance, or historical MVP result is rewritten.

## Source and execution contract

For the reviewed s1 program only, the verifier binds the supplied original source hash and original argv to the preserved original OOM Lab run. The original source must match the pinned complete-program AST and must not already contain checkpointing. A fixed versioned transformation changes the existing block invocation to the official non-reentrant checkpoint API, with RNG preservation explicitly enabled. Everything else, including model, batch, inputs, targets, SGD settings, loss objective, and loop, is preserved by the complete-program AST contract.

The transformation is constructed from the original source, never from the candidate. It is written to a new exclusive directory beside the candidate's evidence. The receipt records transform version s1_non_reentrant_blocks.v1, original/transformed SHA256, original argv, required 20 logical updates, and the bounded reference duration. After the separate Lab execution, the verifier checks the actual wrapper manifest, source capture, and a fresh deterministic reconstruction of the transformed source.

Both the reference and candidate must provide actual initialized tensor and parameter fingerprints, stable inputs, and complete per-update observations. Checkpoint recomputation roots are recorded separately from ordinary training forwards. Known reference precision must match the original baseline; the original scalar tolerance and candidate precision policy are unchanged. Candidate memory/performance are measured from the candidate alone.

[The pinned PyTorch 2.5.1 implementation](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/utils/checkpoint.py) supports the reviewed non-reentrant API. This program has no random operation inside its residual blocks, running-stat updates, stateful forward mutation, or gradient accumulation. This bounded contract is not a general proof that arbitrary checkpointed programs preserve semantics.

## Failure and resource boundaries

Exactly one transformed reference is attempted per verification. Preparation, execution, provenance, precision, pairing, timeout, or cleanup failure leaves the new proof false. It never falls back to a small-batch reference, and the new strategy cannot use the repository no-reference exception to turn a missing proof into success.

The strategy requires 20 complete logical updates, keeps the reference limit at no more than 480 seconds, and does not enable CPU or disk saved-tensor offloading. Customized offload resource fields are rejected. The ordinary Lab container memory and GPU isolation limits remain in force.

Configuration example:

    numerical_reference:
      strategy: original_workload_checkpoint
      max_seconds: 480

NumericalReference.verify_kwargs passes only reference_strategy and reference_max_seconds for this strategy. The shared schema carries it through FixRequest/config/API/evaluation, and the CLI strategy enum is maintained by the root task.

## CPU verification

The dedicated tests cover fixed deterministic transformation, original/source argv mismatches, independently captured initial state, actual transformed source after execution, unsupported precision, unknown precision, missing recomputation, changed batch, incomplete steps, cleanup failure, and refusal to use caller-supplied pairing to bypass proof. Failed OOM/timeout/error references are attempted once with the original argv and never trigger the legacy path.

A real CPU-wrapper test runs the original tiny workload, candidate, and derived reference for 20 updates. All loss values match exactly; the reference records 40 checkpoint recomputation roots and actual source/argv provenance. Only the OOM branch trigger is emulated in that CPU test, explicitly documented in the test; this is not evidence of a real GPU OOM or full-size acceptance.

Validation command:

    .venv/bin/pytest -q tests/test_verify_checkpoint_reference.py tests/test_pairing.py tests/test_verify_offload_reference.py tests/test_numerical_reference_options.py

Result before root's additional CLI transport tests: **124 passed in 66.83 seconds**. Ruff passed. No model or GPU was called by these tests.

## Single GPU resource calibration protocol

The preserved v7 s1 OOM run fb2d52bc58d4417b8b54879ba67382f1 has the correct original source SHA and argv, but its old pairing implementation supported only s3/s4. Its input fingerprints and initial parameter fingerprints are absent. They cannot be reconstructed into historical runtime evidence by assuming the same seed.

Consequently the resource calibration is explicitly separate from production proof. It may derive one transformed source from the verified historical source and argv and run it once to determine whether the full workload fits and completes within 480 seconds. It must retain original_baseline_pairing_proven=false and must not count a model success. The strict production preparation/proof is not weakened to allow the old capture.

The initial unexecuted plan is runs/research/s1-checkpoint-reference-20261025/plan.json. Its source hash was invalidated before any execution, and it is retained. The executed v2 plan is runs/research/s1-checkpoint-reference-20261025-v2/plan.json.

V2 run c079b92990a74fe1833b68fce0abe021 completed 20 updates in 84.157571 seconds at a peak of 14,297,204,736 bytes. Its strict result remains false: the old precision observer reported unknown for checkpoint graph metadata and CUDA worker recomputation. The original-baseline pairing proof remains false because historical inputs and initial parameters were not captured. Later stat inspection also found snapshot.json is 1,284,045,979 bytes, above the unchanged 536,870,912-byte loader gate. The original receipt and snapshot are retained.

The precision defect was repaired and validated in two bounded real CUDA observer regressions, documented in reports/checkpoint-precision-observer-20261025.md. The separately reviewed lossless snapshot codec then passed 301 consumer-focused tests; the final hooks/precision/reference integration passed 107 focused tests. These results do not relabel v2 as passed.

The future formal MVP baseline run will naturally capture the newly supported s1 actual inputs and initialization. Only that fresh evidence can close the full original-baseline pairing proof. Resource feasibility alone cannot do so.

## Completed v3 resource and observation qualification

The one preregistered v3 reference completed successfully. It is a baseline-derived transformed resource control, with no candidate run and no model call. All 13 resource, source-binding, precision, capture, cleanup, and reader checks are true. It is not a model repair or an additional MVP success.

| Observation | V3 result |
|---|---|
| Reference run | b6ea4ee5fd3144a3adae57ffb05f9d8f |
| Complete logical updates | 20 |
| Wall time / unchanged limit | 115.271469 seconds / 480 seconds |
| GPU peak allocated | 14,297,204,736 bytes |
| Actual observed precision | Complete FP32; no observer errors |
| Checkpoint worker entries / exits | 3,840 / 3,840; zero failures |
| Operation-mode entries / exits | 3,860 / 3,860 |
| Encoded snapshot / unchanged reader limit | 27,640,271 / 536,870,912 bytes |
| Decoded snapshot | 441 segments; 200,000 trace events |
| Original analysis entry | read_snapshot_artifact then analyze_snapshot: passed |
| Original pickle | Retained, 42,972,855 bytes |
| Exclusive GPU / cleanup / pinned source unchanged | All true |

The codec preserves the existing captured events and stacks without dropping them or raising the reader gate. The 200,000 events are those in the existing bounded snapshot; this is not a claim that the capture contains an untruncated history of every training event. The reference performance is excluded from candidate performance scoring.

Evidence lives at runs/research/s1-checkpoint-reference-20261025-v3/plan.json and calibration.json. Plan SHA256: 08bf8cb135165b8616fe680536825024254a391f148b4f4035ca75e17c8d4998. Calibration SHA256: 264297c684a1daa9f14ce7ac2134f605c0fad9d1a985173cf6a9d9c98cc5c646. Snapshot SHA256: 390eb9b468dd91388049211cb9951a1ac521a37cd2a1a90a1d1254e1a81a7529.

The full reference proof deliberately remains false: this calibration has no candidate, and the historical original OOM has no observed input or initialization fingerprints. The new formal campaign must capture a fresh original baseline and independently verify its actual candidate. No historical score, tolerance, threshold, or receipt was rewritten. GPU release was confirmed after the run.
