# Verification and comparison

Status: offline implementation with real CPU Docker checks. **T1.6 is not yet
accepted.** The original full-size s1 repair, s3 saving of at least 30%, and s1
half-model rejection still require their actual GPU repair evidence. No Nebius
call or new GPU workload was used to implement this layer. Existing historical
GPU results are read-only evidence and are not converted into new repair results.
The original plan and its acceptance thresholds remain unchanged.

## Interfaces

```python
from headroom.verify.compare import compare_runs

report = compare_runs(
    baseline_result,
    candidate_result,
    target="fit:22GB",  # also fix-oom, reclaim, fit:22GiB
    reference=small_batch_result,  # required for numerical comparison of an OOM baseline
    pairing=None,  # optional diagnostic proof; never inferred from a shared seed
)
json_payload = report.model_dump()
```

`VerifyReport` contains the original fields: completed, peak_before, peak_after,
reduction_pct, step_ms_before, step_ms_after, loss_equivalence, target_met and
notes. It also exposes checks, max_loss_delta, throughput_regression_pct,
numerics_changed, parameter_count_before/after, target, run IDs and reference path.
Peaks use decimal GB (1e9 bytes); input bytes remain the authoritative measurement.
A GiB target is explicitly converted using 2^30 bytes.

Canonical policy keys are `allow_numerics_change=False`,
`allow_model_change=False`, `allow_batch_grad_accum=True`, and
`max_throughput_regression_pct=25`. No model count is accepted from an external
parameter_counts override or a user-script-written verification.json.

`headroom.verify.runner.verify_script(baseline, candidate_script, ...)` runs the
candidate only through the existing Lab Docker interface and returns:

```text
{"report": VerifyReport, "candidate": Lab result,
 "reference": Lab result or None, "reference_discovery": discovery/attempt evidence}
```

Its keyword arguments include baseline_script, script_args, baseline_args,
candidate_source_root, baseline_source_root, run_root, target, policy, pairing,
reference, device, seed, required_steps=20, max_seconds=120, allocator_conf and
baseline_allocator_conf. Comparison options such as precision/numerics_impact are
forwarded to compare_runs. The wrapper writes verification.json into the new
candidate run directory using exclusive creation; old runs are preserved.

## Numerical evidence and original rules

The original fp32 bound remains 1e-3; permitted bf16 changes use 2e-2 and are
explicitly marked numerics changed. Callers may tighten these bounds, not relax
them. The four loss states are identical, within_tol, changed and n/a. They
classify the **observed scalar comparison prescribed by PLAN C.5**, not a proof
that arbitrary programs process the same workload. A denied model parameter
change is changed even if the observed losses match. Missing or nonfinite
candidate losses cannot satisfy the training acceptance gate.

Candidate completion still requires the requested optimizer update count
(default 20), valid capture and verified cleanup. Backward scalar count is a
separate quantity: gradient accumulation can legitimately capture several
scalars per optimizer update. For an OOM baseline, the candidate must have finite
losses and a lower final than initial loss. The original small-batch reference
must complete the same requested update count with the same recorded seed;
comparison uses the first five backward scalars from each run. Reclaim compares
both complete, finite, equally long scalar sequences. Unequal sequence lengths
are n/a; they are never silently truncated, averaged or divided by accumulation.

The optional same_inputs, same_effective_batch and same_objective observations
remain true, false or unknown as actually measured. loss_comparable additionally
reports whether these stronger conditions are established. Their absence is
visible in notes and does not add an unapproved global acceptance requirement.
Equal seed values alone do not prove those conditions. Numerical basis is
recorded separately, so an observed original-plan delta is distinguishable from
stronger runtime pairing evidence.

Standard script verification requires the applicable original numerical check.
The trusted repository command entrypoints select acceptance_scope=repository:
PLAN T1.9 explicitly permits an OOM repository candidate with no available
reference to retain loss_equivalence=n/a. Only that case receives the
repository_no_reference_exception; finite/decreasing candidate losses, optimizer
updates, seed setup, parameter preservation, policy and measured memory gates
still apply. A provided but failed reference, a failed tolerance, or a requested
precision change cannot use this exception. Reclaim cannot use it either.
The keep/revert decision checks the same scoped exception and reports numerical
equivalence as unverified. It does not promote n/a to identical or within_tol.

Section F's missing-loss/inference fallback permits an honest n/a report; it
does not by itself waive every training acceptance check or define successful
inference output. This implementation does not manufacture optimizer steps or
convert an actual watchdog timeout into completed execution.

**Correction on 2026-10-24:** earlier implementation treated pairing proof and
exactly one backward scalar per update as global hard gates. Those gates were
not in the retained original plan, and the user had not approved the proposed
numerical-plan revision. They have been removed from mandatory acceptance while
their measurements and limitations remain visible. Existing historical results
are unchanged. Original loss tolerances and scenario-specific acceptance
requirements have not been reduced.

The real CPU fixture in tests/test_verify_runner.py uses fixed torch.arange
input, fixed labels, identical batch/model, identical seed and 20 updates. Its
half-width model has different measured parameters and a loss deviation above
1e-3; it is rejected. This CPU fixture does not prove the s1 GPU acceptance case.

## Measured memory, timing and parameters

Only successful Lab captures with verified cleanup and the requested update count
are eligible. CUDA allocated peak bytes must exist, be positive integer counts,
and fit the recorded device capacity. Reserved-memory changes are never relabeled
as live allocated-memory savings. CPU runs expose no CUDA peak and cannot pass a
GPU memory target. Reclaim requires a completed baseline and defaults to a 30%
allocated-peak reduction; an explicit target percentage may be supplied. A fit
boundary is inclusive. The scenario-specific s1 requirement peak_after <24GB
still needs its separate original acceptance check.

The measured step-median change must satisfy the policy's 25% default bound for
reclaim. Matching recorded GPU hardware and clear, complete GPU observations are
required for throughput. Existing Lab samples do not establish continuous
exclusivity; shared or incomplete observations prevent a reliable timing verdict.
They do not independently reject an OOM memory-capacity result, following PLAN F. An OOM run
has no completed-baseline throughput comparison, which is reported as unknown,
not as an invented speedup. OOM peak reductions compare observed peaks only;
they do not estimate the unobserved memory needed to finish the failing baseline.

Lab hooks now observe actual root forward module.parameters() and module parameter
registration. Registered parameters are held only by weak reference; shared/tied
parameters count once. Root forwards and optimizer updates sample unique live
registered parameters, including registered unused models. Count, source,
observations, root counts and coverage notes are saved in result.json. No CUDA
tensor is copied, retained or deliberately freed by these hooks.

A missing root forward, changing observed count or observation error leaves the
parameter coverage incomplete. Standalone tensors and pre-capture unused modules
are outside this coverage. Parameter counts are runtime observations, not
cryptographic authentication against a malicious target that disables hooks.
Old captures without this evidence cannot silently pass the model-preservation
gate; they must be rerun through the updated Lab. This layer does not claim that
equal parameter counts alone prove equal architecture or objective—the independent
patch policy remains mandatory, and optional workload pairing reports its
additional evidence without becoming a global requirement.

## Small-batch reference discovery

No script is imported on the host. Discovery statically inspects argparse
add_argument declarations for --batch, --batch_size or --batch-size. headroom.yaml
can explicitly map a CLI argument:

```yaml
batch:
  arg: --batch
  value: 32
```

The equivalent `batch_arg: --batch` and `batch: 32` fields are also accepted.
Configuration uses safe YAML parsing, a 16 KiB bound and regular files only.
Unknown, ambiguous or unsafe configuration causes no guessed reference run.
Configuration-only training options without an explicit CLI mapping are reported
as undiscoverable; arbitrary user configuration code is not executed on the host.

The reference always uses the original script and original baseline arguments,
with only the discovered batch replaced. If baseline_args is omitted, arguments
are recovered from the saved Lab manifest; candidate patch arguments are never
silently substituted. The smallest positive batch, 1, is tried first. Successful
completion selects it. Bounded subsequent trials can handle a script rejecting a
particular positive value; OOM, timeout or GPU-unavailable results stop exploration.
The default maximum of four attempts limits execution only: failure or exhaustion
leaves the reference unavailable; only the original repository no-reference
exception may then apply. Every attempt retains its run directory.

## Verification commands and evidence

```sh
uv run pytest -q tests/test_compare.py tests/test_verify_parameters.py tests/test_verify_runner.py tests/test_lab_hooks.py --basetemp=runs/verify-tests-<unique-id>
uv run ruff check headroom/verify/compare.py headroom/verify/runner.py headroom/lab/hooks.py tests/test_compare.py tests/test_verify_parameters.py tests/test_verify_runner.py
```

Use a fresh basetemp for each test invocation, since pytest clears an existing
basetemp. The first integration execution is retained under
runs/verify-tests-20261024-a: 50 checks passed, including real CPU sandbox runs,
parameter lifetime/deduplication, half-model rejection, the existing Lab hook
regressions, and read-only comparison of historical GPU captures.

The final focused invocation used runs/verify-tests-20261024-c: **54 passed in
8.37 seconds**; Ruff passed. The intermediate -b invocation is also preserved
(53 passed, one new peak-validation regression failed and was repaired before
the final run). All parameter/loss CPU evidence remains in those run trees.

Root later reran the original T1.1 GPU acceptance with these parameter hooks:
reports/lab-gpu-acceptance-20261024T021625Z.json. The report records all original
checks true, s1 CUDA OOM with 2,050 device events and 101,007,360 parameters
(coverage complete), and two s3 20-step runs with identical first-five losses and
37,791,744 parameters (coverage complete). All containers were cleaned up and
GPU samples were unshared. These are baseline/capture regression results, **not
T1.6 repaired-GPU acceptance or a measured repair saving**.


## Automatic pairing evidence: bounded s3/s4 production support

The default verify_script path now derives same_inputs, same_effective_batch,
and same_objective from pairing_capture artifacts. It does not infer them from
equal seeds, argv, config, target stdout, or a target-supplied claim. Detailed
pairing_evidence is saved in the candidate verification.json and returned to
the orchestrator. Existing historical runs without these observations remain
unknown; they are not retroactively upgraded.

Support is intentionally limited to the complete standalone s3/s4 program ASTs
pinned in headroom/verify/pairing.py. Whitespace and comments do not affect the
contract. The only accepted AST differences are:

- s3 evaluate wrapped in torch.no_grad() as a decorator or a top-level with
  block; its underlying body stays identical.
- s4 loss.backward(retain_graph=True/False) or loss.backward(), and the
  total_loss metric accumulation using loss, loss.item(), loss.detach(), or
  loss.detach().item(), with the corresponding emit total_loss value. The
  backward_retain_graph reporting boolean may change.

All other source changes, including data or target construction, loss
expression, model, learning rate, training no_grad, or batch defaults, are
unsupported and explicitly unknown. This is a reviewed source contract, not a
generic proof for arbitrary Python. Command-mode capture and unsupported
external repositories remain unknown. Explicit caller-supplied pairing remains
a separate labeled compatibility/testing seam; production automatic proof does
not use it.

For supported programs, a short initialization tracer reaches the reviewed main
loop before its first timed operation, hashes the actual fixed training and
evaluation inputs/targets plus initial named parameters, then removes itself.
The SHA-256 fingerprints include dtype and shape and are bounded to 512 MiB
total tensor bytes. Only weak references and fingerprints survive capture.
Root forwards, backward caller/frame objects, tensor mutation versions, and
actual optimizer hooks verify one training forward/backward per update on the
captured tensors. Effective batch is the observed training tensor leading
dimension per actual update. Missing coverage, capture errors, mutation,
unexpected updates, or a preexisting Python tracer make proof unknown.

Before starting the hash timer, capture synchronizes the observed CUDA devices,
so pending target initialization remains in the Lab interval. Initial hashing
time is recorded separately and deducted once from the first Lab optimizer interval. Total wall time and the execution deadline retain it;
ordinary hook/tracer overhead is not claimed to be eliminated. No per-step
tensor copies or hash operations are added. Initial model parameters must match
as an additional objective condition. Pairing is evidence for cooperative
targets, not authentication against a program deliberately rewriting hooks.

CPU Docker regressions exercise real s3/s4 baselines and legal repairs without
passing synthetic pairing flags. They prove actual identical loss and pairing,
not GPU memory savings or throughput acceptance. Changed runtime batch produces
mismatched input/effective-batch proof; changed target source stays unknown.
Original numerical thresholds, required optimizer steps and batch-policy gates
remain enforced. Small-batch OOM reference versus a different effective batch
still lacks stronger pairing proof, but C.5's first-five-scalar check is evaluated
and labeled as such. The fingerprints do not limit general-script eligibility.


### Full-size CUDA regression after the CPU checks

The root continuation subsequently exercised the original s3 workload and a
manually written no_grad decorator in two real 20-step GPU Lab runs. The default
verifier derived all three pairing checks from actual captures and reported
identical training losses, unchanged parameters, a 73.3787% peak reduction and
0.3333% longer measured optimizer intervals. All capture/cleanup/unshared checks
passed. See `reports/pairing-manual-gpu-20261024T111357Z.json` and `docs/RESULTS.md`
for exact bytes, times and reproduction. This is an instrumentation/verification
regression for a known manual repair; it is not a generated model repair, general
script support, or closure of the remaining T1.6/MVP/evaluation gates.


### Original-plan comparison through a Python module command

A subsequent manual GPU regression used `python -O -m train` for both baseline
and candidate. A harmless module constant was added to a copy of s3 so its AST
was outside the pinned pairing contracts; the candidate added only the known
`no_grad` repair. Both isolated runs completed twenty optimizer updates, cleaned
up and observed an unshared GPU. Peak allocated memory was 2,435,717,632 versus
648,419,840 bytes (73.3787% lower); the full captured loss sequences matched
exactly. Median optimizer intervals were 41.3288 versus 40.5021 ms.

The default verifier used standard script acceptance and the original full-loss
comparison. All three stronger pairing observations remained unknown and
loss_comparable remained false. This confirms that module/flag replay and the
retained original numerical rule work without a pinned program exception; it
does not establish general workload equivalence or a model-generated repair.
Receipt: `reports/command-manual-gpu-20261024T113103Z.json`.


## Observed precision and the original tolerance

The production verifier now selects its comparison precision from
`result.precision_observation`, captured inside the Lab. It distinguishes an
observed dtype from a change of dtype: BF16 baseline → BF16 candidate does not
by itself require permission for a new precision change. FP32 → BF16 is marked
`numerics_changed` and requires the existing policy permission, even when a
proposal labels its numerical impact as none. The original loss bounds remain
1e-3 for FP32 and 2e-2 for observed BF16 comparisons. Explicitly requested tighter
bounds remain tighter; insufficient, mixed or unsupported observations do not
automatically increase the tolerance. Old captures without precision evidence
retain the FP32 bound rather than gaining a new global rejection gate.

The observer reads parameter, input and output dtype metadata at module hooks,
and samples Python-dispatched tensor operations during root forwards. This
captures functional autocast inside a forward even when the final loss is cast
back to FP32. No tensor data is copied or hashed, no tensor reference survives
the observation, and no GPU synchronization is added. Counters and metadata
traversal are bounded. Known compiled/scripted modules, mixed root modes,
unsupported dtypes, errors and insufficient coverage remain unknown. These are
runtime observations, not proof of every native operator's internal dtype.

The operation mode is entered only for an observed root forward and restored
when it returns, with capture cleanup as a fallback. It is not active around
ordinary optimizer or backward execution. Same-Tensor dispatcher reentry is
recorded once; different nested losses and subsequent backward calls remain
observable. Precision observation overhead remains in reported optimizer-step
intervals; no overhead-free performance claim is made.

`VerifyReport` and per-round report tables expose `comparison_precision`,
`loss_tolerance`, `observed_precision_change` and the supporting
`precision_evidence`. The direct Python comparison interface still accepts an
explicit `precision` for trusted callers and labels that override; model output
cannot select this override in the production orchestration path.
