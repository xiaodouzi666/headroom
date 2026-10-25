# Numerical context repair: r2 offline review

The r1 failure is preserved. This change exposes observations the Lab had already captured and describes the verifier's supported edit boundaries. It does not change numerical acceptance or certify a model repair.

## Observed r1 failure

Campaign 20261025T095016638167Z-ad191318, s1 job 9d1890409c4d4244939cbf8b98d73c82, original Lab run 999a21fb1cef45948fe3af63f5cfe11b ended OOM before any optimizer update. Its raw capture includes initialized input shape [32, 2048, 256], target shape [32, 256], FP32 metadata and tensor fingerprints, bound to the retained source. The old context helper required all 20 updates before exposing any of these fields, so it hid valid initialization observations together with genuinely missing update evidence.

The actual diagnostic request did carry the selected original_workload_checkpoint protocol and its unsupported-microbatch boundary. The model nevertheless proposed microbatch accumulation and requested runtime information before continuing. No s1 candidate or reference was executed in this r1 job.

## Repair and limits

- initial_tensors exposes only validated, source-bound initialization metadata. Partial or failed initialization, malformed tensor hash/shape, different source, missing run identity or incomplete finalization remains unavailable.
- logical_updates remains separate. An actual OOM with zero observed update calls can be described as not_reached; it does not establish an effective batch or a successful update boundary. Overall status and target configuration stay unverified.
- Completed, consistent 20-update captures retain their existing fields. Bad counts, order, backward counts or batch association do not establish update completeness.
- The evidence catalogue gives the components separate exact references. A visible initialization component cannot disprove a missing update component. The final 8 KiB bound remains; the fixed-field count includes both children.
- Explicit reference context describes the existing narrowly supported non-reentrant checkpoint family and its import, RNG, argument and unchanged-program constraints. It contains no replacement code or manual control result. Every candidate still must pass the unchanged source contract and actual verification.

Microbatch accumulation remains outside the reviewed pairing contract. Its certification would require actual slice coverage and association, objective weighting, complete optimizer-update boundaries and comparable aggregated losses. Equal seeds and effective-batch arithmetic alone do not provide those observations.

## Public basis and engineering inference

PyTorch's pinned [2.5.1 checkpoint source](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/torch/utils/checkpoint.py) documents activation recomputation and the non-reentrant/RNG interface. Hugging Face's [accumulation guide](https://huggingface.co/docs/accelerate/usage_guides/gradient_accumulation) describes scaling losses and updating the optimizer after accumulation; variable-size losses require their actual denominators.

Separating initialization observations from update completeness is this project's engineering inference from its raw evidence. Neither source certifies this implementation, guarantees a candidate's memory fit, or supplies missing runtime pairing proof.

## Validation and independent review

The isolated CPU/mock focused run passed **89 tests in 1.52 s**. Ruff check and format check passed. Cases cover OOM initialization, malformed hashes/shapes, missing tensors, incomplete captures, different sources, bad update metadata, complete 20 updates, exact child catalogue/schema behavior, size/count limits, and supported versus unsupported reference descriptions.

The reliability reviewer independently inspected the diff without editing production or rerunning tests. No blocking proof relaxation was found. Its suggestions—precise top-level single-name import wording and the fixed catalogue entry count—were incorporated and the focused run repeated.

After root integration, all three production modules and the new test file matched the final reviewed private SHA values. The JSON receipt records before/after hashes, review scope, the test log and replay hashes.

## Evidence files

- numerical-context-review.json: source bindings, focused test receipt, independent-review summary and limits.
- numerical-context-review-tests.log: original focused-test output.
- numerical-context-review-r1-replay.json: read-only old/new context comparison against unchanged r1 raw artifacts. Its catalogue is an isolated helper fixture, not a complete HTTP replay.

These public files contain no source bodies, manual candidate bodies, provider prompt/response bodies or credential values. No GPU run or model call was made for this repair. No historical outcome was updated. Full production regression and a new live campaign remain separate acceptance stages.
