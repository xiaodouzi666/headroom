# Candidate reference preflight — 2026-10-30

The R11 s1 first candidate completed 20 optimizer updates and reduced measured peak allocation from 24,750,424,064 to 17,112,406,528 bytes. It did **not** establish numerical equivalence: the selected checkpoint reference protocol rejected its unsupported source family before preparing a reference. The original result remains false / `loss_equivalence=n/a`; no historical result changed.

## Read-only diagnosis

- Actual patch keeps `zero_grad` outside the microbatch loop, weights each chunk mean by `4/32`, and steps SGD once. For this fixed batch32, sample-independent LayerNorm/MLP/MSE source, the mathematical full-batch gradient objective is plausible. Floating-point reduction/order differs and no paired numerical comparison was observed. This audit does not certify equivalence.
- The existing `loss` variable used by the step logger is only the last chunk's mean scaled by 1/8. Captured backward scalars number160 for20 logical updates. A scalar capture is not an optimizer update. Existing comparison metadata explicitly provides no microbatch aggregation or automatic loss rescaling.
- The original selected capability context already forbids arbitrary training-loop, objective and gradient-accumulation rewrites, and requires one training root forward/backward per update. Its complete normalized-program contract admits only reviewed edit families; the checkpoint family preserves the existing per-block call and requires non-reentrant checkpointing with the exact listed import/RNG/argument restrictions. These are capabilities, not a generated patch or runtime guarantee.
- Both diagnostic and patch requests receive that context through `solver_prompt_context`. It preserves the complete fixed capability metadata; history bounding only removes oldest candidate/verification rounds. The failure was not evidence truncation of that boundary.
- Before this change, `verify.runner.verify_script` executed the candidate at line214 before evaluating checkpoint `source_contract` prerequisites around315. The deterministic inability to compare could thus be discovered after consuming a GPU candidate run.

## Minimal implementation

`headroom/verify/candidate_preflight.py` reuses the exact existing bounded source inspector. Only an already active explicit OOM source-contract boundary and a known original normalized contract allow static rejection. A known unsupported candidate or different supported normalized contract is rejected; missing/unknown metadata does not become a fabricated failure or equivalence result. A matching contract admits only the existing runtime verifier.

After an applied patch and before `services.verify`, orchestration records the receipt and, for static rejection, reverts the current bounded round and continues within the original maximum6 rounds. It retains the patch and receipt, does not create a fake candidate Lab run or `verification`, and does not modify retained source/state, target, numerical gates, policy or budget. Next-round feedback includes the exact static rejection and points to the already available reviewed edit-family requirements. The receipt states no runtime or equivalence proof.

`solver_context.py` adds the capability reading aid and the root agent's retained-state reading aid to both request builders under the existing64KiB combined bound. A rejected preflight has an explicit `reference_contract_rejected_before_execution` outcome and unknown numerical comparison.

## Focused verification

- Four guarded offline groups passed: candidate preflight, retained-state aid, numerical reference context, bounded search. See `focused-corrected.log` (59 progress cases). The initial run exposed an unregistered event kind, corrected to existing `run.preflight` with `stage=candidate_reference`; the failed log is retained.
- Final dedicated JUnit: **15 passed**,0 failures/errors,2.123s. Tests exercise real reviewed source/normalized transformation admission, unsupported loop rejection, contract mismatch, unknown/inactive/legacy boundaries, malformed strategy data, both explicit reference families and shared context bounds. The offline SDK integration proves all6 unsupported rounds retain artifacts, run zero candidate verifications, keep the baseline, preserve unknown numerical results, and send the receipt to the next request. These fixtures are not empirical GPU or model acceptance.
- Ruff, formatting and `git diff --check` passed. `verification.json` records source hashes and exit codes.
- No provider HTTP, GPU workload, production-service change, deployment, commit, or spend was performed by this task.
