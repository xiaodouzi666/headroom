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
    pairing=None,  # unknown by default, never inferred from a shared seed
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

The original fp32 bound is 1e-3; permitted bf16 changes use 2e-2 and are explicitly
marked numerics changed. Callers may tighten these bounds, not relax them.
The four loss states are identical, within_tol, changed and n/a. A denied model
parameter change is changed even if its printed losses happen to match. Missing
or nonfinite losses never satisfy acceptance.

For an OOM baseline the original first-five-loss comparison against a small-batch
reference is computed and exposed as max_loss_delta. The candidate must complete
20 updates with finite losses and a lower final than initial loss. A reference
must itself complete the same number of updates. Unavailable references leave
the original numerical gate unmet.

Pairing must describe the candidate versus baseline (reclaim), or candidate
versus small-batch reference (OOM). Keys are same_inputs, same_effective_batch and
same_objective, supplied only by a trusted caller with inspectable evidence. The
implementation never obtains these assertions from arbitrary target output and
does not derive them merely from identical seed values. The Lab's recorded Python,
NumPy and PyTorch seed setup/deterministic mode are checked separately. A seed is
necessary evidence, not proof of the input/data contract.

When pairing is unknown, loss_equivalence is n/a and the strict original numerical
gate stays unmet even if a raw small-batch delta is available. This records a lack
of evidence; it does not amend the plan or adopt the previously proposed acceptance
changes. Generic gradient accumulation can produce multiple backward scalars per
optimizer update. Such an unaligned sequence is not silently reinterpreted or
averaged: an aggregation/data contract is needed before an equivalence claim.

The real CPU fixture in tests/test_verify_runner.py provides an inspectable paired
case: fixed torch.arange input, fixed labels, identical batch/model, identical
seed and 20 updates. Its same-model losses are checked for exact equality. Its
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
required. Existing Lab samples do not establish continuous exclusivity; shared or
incomplete observations prevent a reliable timing/capacity verdict. An OOM run
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
patch policy and workload pairing checks remain necessary.

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
leaves reference/acceptance incomplete. Every attempt retains its run directory.

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
All original numerical thresholds, required steps, GPU checks, and batch-policy
gates remain unchanged. Small-batch OOM reference versus a different effective
batch remains non-comparable; its original numerical-policy question is pending.


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
