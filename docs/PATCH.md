# Patch generation and static honesty

Implementation of T1.5 and the static portion of T1.10. This document describes
the implemented boundary, not live-model or GPU acceptance.

## API

- `PatchEngine(router, max_repairs=3, max_completion_tokens=4000)` requires the
  existing Token Factory `LLMRouter`. Role `patcher` selects Nemotron Super.
- `engine.generate_and_apply(source_root, plan_step, work_root=..., policy=None,
  source_files=None, base_cli=(), context=None)` accepts a dict or an object with
  `model_dump()` for the plan step. Pass sanitized evidence in `context`.
- `apply_proposal(source_root, proposal, work_root=..., policy=None,
  base_cli=())` checks and applies an already generated proposal, without LLM calls.
- `scan_source_forbidden(source, source_files=None)` accepts a directory or a
  mapping such as `{"upload.py": script_text}`. API upload handlers must reject
  `report.allowed == False` before submitting source or executing it.
- `check_parameter_counts(before, after, policy=None, notes=())` consumes observed
  integer parameter counts from Verify. Missing counts fail closed; equal counts
  alone do not prove model or loss equivalence.

All results are dataclasses and support `dataclasses.asdict()`. Paths in
`PatchResult` are strings. Useful fields are `applied` (property), `status`,
`reason`, `candidate_dir`, `patch_path`, `env_changes`, `cli_changes`,
`effective_cli`, `attempts`, `policy_report` and `runtime_verified`.
The last field stays false: patch application never runs the training target.

`PatchPolicy` defaults:

| Field | Default |
|---|---|
| allow_numerics_change | false |
| allow_model_change | false |
| allow_batch_grad_accum | true |
| allow_batch_change | null; explicit false vetoes |
| allow_grad_accum | null; explicit false vetoes |
| max_throughput_regression_pct | 25 |

The throughput field is carried through to the runtime verifier. Static policy
does not fabricate a performance measurement.

## Structured output and request limits

`PatchProposal` is a strict Pydantic object with only `diff` (string),
`env_changes` (string mapping), `cli_changes` (string array), and optional
`notes` (string array). Unknown fields and coercions are rejected. Diff size is
at most 512,000 bytes and 20 files. Model context contains line-numbered source,
at most 128 KiB of raw source text. Whole files that do not fit are listed as
omitted; no partial source is silently presented as complete.

The engine sends one initial request and at most three repair requests. Every
request uses `max_tokens <= 4000` and explicit `reasoning=False`, including
fixer requests. The verified model capability chooses the supported control;
this does not raise or replace the original completion cap. Reported completion
usage must be present and within the cap before application. A missing/oversized
usage report is not retried. Default client configuration disables live requests. The existing client
owns model identity validation, provider allowlisting, live credentials and
billing; the orchestrator must enforce its run-wide money cap. Offline
MockTransport tests do not verify real model capability, pricing, or token counts.

## Private response evidence and the applied protocol revision

Every patch/fixer request now attempts to save
`attempt-1-response.json` through `attempt-4-response.json` in its private
engine directory before candidate application. A `ResponseValidationError`
contributes its attached response, so rejected schema/truncation output is not
lost merely because `router.chat` did not return normally. When no response
object exists, available protocol records remain explicit metadata rather than
invented content. `PatchAttempt.response_artifact` identifies the saved file.

Each artifact is at most **256 KiB** of UTF-8 JSON. It records visible assistant
text, parsed proposal and diff where available, original content byte counts
and SHA-256 digests, finish/validation metadata, usage and protocol-cost data.
Large parsed objects are explicitly omitted; retained visible/diff prefixes are
marked truncated and cannot be treated as complete patches. There is no stored
request payload, request headers, credentials or hidden reasoning text.
Reasoning-token *counts* may remain in usage metadata. These files are untrusted
diagnostic evidence, not executable input or automatically public downloads.

Publication pins every directory component with no-follow directory handles,
requires the private parent directory to be mode 0700, and creates mode-0600
temporary files with O_EXCL/O_NOFOLLOW. Atomic exclusive publication never
overwrites an existing attempt artifact or follows a destination symlink.
Only this writer's new temporary file is cleaned up on failure.

**Store and BudgetLedger remain the financial authority.** The response
artifact's protocol records describe an observed response/cost calculation;
they do not prove ledger settlement or authorize continued dispatch. If evidence
writing fails, the failure propagates and no replacement model request is made
to regenerate the artifact. Existing financial records and pending/unknown
protections are not cleared. On a failed model call, the original exception is
preserved with the evidence failure noted; interruption/budget exceptions are
not converted into ordinary patch retries.

MVP v2 preserved 16 failed Super attempts, with no apply/compile/candidate
execution. The historical raw diff payloads are absent. Offline checks prove
that both ordinary unified diff and a matching optional git header are accepted;
different malformed inputs yield the same file-count error. The new prompt
wording clarifies that existing format, rather than relaxing the parser or
guessing what the unsaved historical payloads contained.

The explicit reasoning control and private evidence code have been applied.
Current production-tree targeted integration passed 294 guarded tests, including CPU Docker; the next live
attempt has not run. No new model-repair success or real-scene acceptance is
claimed. See [application record](../reports/super-patch-fix-20261025/application.json),
[standard-diff check](../reports/unified-diff-contract-20261025.json),
[error ambiguity controls](../reports/unified-diff-contract-20261025-supplement.json)
and [MVP v2 findings](../reports/live-campaign-20261025/mvp-v2-repair-findings.md).

## Copy, apply, compile and evidence

Each engine invocation freezes a baseline copy. Each candidate gets a distinct
UUID directory and is applied to that baseline, including repair attempts.
Existing inputs and previous failures are never overwritten or removed.
Lab `copy_source` excludes credentials, environment files, Git metadata,
symlinks and dependency/cache trees. The source manifest records names, sizes
and hashes, without file contents.

Before context construction, source preflight rejects recognizable literal
credentials (including sk-/tvly-/HF/GitHub/JWT patterns), credential variable
access, environment-file loading, network/process/dynamic execution imports
and calls, and obvious filesystem escape. Results contain reason codes and file
positions, never matched credential values. A named `.env` file is excluded
without opening it. `import socket` in an uploaded Python script is rejected.
Explicit `source_files` limits inspection and model context; use actual training
entry/model/config files. Unrelated download/preparation scripts can otherwise
cause a conservative rejection. The scanner does not silently exempt a known repository. See the explicit pinned
nanoGPT profile below for its reviewed local configuration loader.

The candidate has its own Git repository and staged baseline, with no commit
created. Host/global/system Git configuration, hooks, fsmonitor, templates and
Git protocols are disabled. Commands are argument arrays with `shell=False`.
Application runs `git apply --3way --check` and `git apply --3way`. A diff without
blob IDs may use Git's documented direct-application fallback; `apply_mode`
records that fallback instead of claiming a three-way merge occurred.
Without Git the operation fails closed with `GIT_UNAVAILABLE`.

Only safe relative paths and supported source/config extensions are accepted.
Traversal, symlink targets, Git/credential metadata, rename/copy/delete, binary,
executable/symlink/submodule mode changes are rejected. Python files then go
through `python -I -S -m py_compile` using a minimal environment. No target
imports, training, network calls, GPU work or target subprocesses occur.

Artifacts include `result.json`, per-attempt JSON, `source-manifest.json`,
`patch.diff`, candidate source, `env.sh`, and `cli.json`. Failed candidate
directories remain available. The env sidecar only exports validated
`PYTORCH_CUDA_ALLOC_CONF` values. It is not executed by this module.
CLI changes are allowlisted long-option overrides. The caller must use
`effective_cli`, which preserves unrelated original options, rather than
treating the override list as a replacement command.

## Honesty checks and limits

Static checks reject detectable layer/hidden/vocabulary/sequence or constructor
dimension changes; reduced or removed training/data/loop bounds; additional
break/continue; removed backward/update calls; model-construction deletion;
forbidden casts, autocast, numeric dtype strings and precision config overrides;
and newly introduced unsafe operations. Model changes require both explicit
policy permission and a note containing `MODEL_CHANGE_APPROVED`.
Known batch and accumulation values must preserve their product; unknown
effective-batch/data-order equivalence still requires runtime evidence.

Reason codes include `MODEL_SHRUNK`, `MODEL_CHANGED`,
`TRAINING_TRUNCATED`, `NUMERICS_CHANGE_FORBIDDEN`,
`EFFECTIVE_BATCH_CHANGED`, `NETWORK_OR_PROCESS_FORBIDDEN`,
`FILESYSTEM_ESCAPE`, `EMBEDDED_CREDENTIAL`, `ENV_FILE_ACCESS` and
`PARAMETER_COUNT_UNVERIFIED`.

Static Python analysis is conservative and incomplete. Dynamic aliases,
indirection, adversarial encodings, conditional training skips, framework
internals and all possible data truncations cannot be proved safe here. Existing
operations may be tolerated by diff-level checks; ingress preflight is stricter.
No static success authorizes arbitrary host execution. Runtime must use the Lab
sandbox, preferably Docker with no network and restricted mounts, and independently
check parameter counts, completed optimizer updates, data/effective-batch
consistency and numerical loss behavior. Parameter-count equality does not catch
unused dummy parameters. Changed batching can alter RNG/dropout/data order even
when the sample count matches.

## Offline validation and remaining acceptance

The focused tests use the real LLM router with `httpx.MockTransport` plus a
DNS/socket denial fixture. All files and temporary Git fixtures stay on azuki
under the project; training code is compiled but never executed.

The suite checks original-file hashes, unique candidate history, bounded repair,
compile-only behavior, schema/path/env/CLI rejection, default live disablement,
completion overrun, source redaction/preflight, cheating reason codes, normal
memory transformations, explicit model-change disclosure, and parameter evidence.

T1.5's actual 8-scene Super generation success rate (at least 6/8 after at most
3 repairs) remains unaccepted. Token Factory access and gifted-credit execution
are available, but MVP v2's s1 failed all 16 patch/fixer attempts before
application, and the other eight campaign cases were operational skips.
T1.10's s1 runtime parameter-count and full normal-patch acceptance still need
real repaired Lab/Verify evidence. Unit tests and the new protocol implementation
do not close either live gate.



## Pinned nanoGPT profile

Both `scan_source_forbidden` and `PatchEngine.generate_and_apply` accept
`source_profile="pinned_nanogpt", sandboxed=True`. This is an internal choice only
for the exact pinned repository; API upload mappings cannot use it, and its caller
must have verified a Docker Lab with no network, read-only source and isolated
output. No host code loads pickle or executes the configurator.

The profile checks the cached original files at `.cache/upstream/nanoGPT`, or the
fixed clean-install fallback `.cache/reviewed/nanogpt/<NANOGPT_REF>`, against
these hashes from ref `3adf61e154c3fe3fca428ad6bc3818b27a3b8291`:

| File | SHA256 |
|---|---|
| train.py | 413bd97b40bb400a2a0d01230e2946f056c263ebac1b7281c2367d964a123085 |
| configurator.py | 5cc23aca26b4ab3c0d9e5f82740f4781f9444f42718c15abcee70d93c5aabe8f |
| model.py | 7c01703240dbec5d554527dc666e35b3df8391d0b117fddc07afcf325a21d11c |

All three files must exist in the selected source tree; the candidate configurator
must remain byte-identical. Only the original AST signatures and occurrence
counts of existing dynamic reads/local configurator execution are allowed, and
only in their original named file. New/changed unsafe operations, network imports,
credentials and environment-file access remain rejected. The original cache hash
check also runs when scanning a patched candidate; changing the cache invalidates
the profile. Copying an extra unsafe expression does not gain an exemption.

`nanogpt_cli(argv)` permits only explicit `--key=value` options, optionally
prefixed with `python train.py` or `train.py`. Positional config files are rejected.
The PatchEngine enforces that rule before model dispatch and emits candidate
`effective_cli` and `cli.json` in equals form. This prevents the configurator's
arbitrary positional config-file branch from being selected by the normal
orchestrator. Policy is still static and cannot prove arbitrary Python semantics.

Focused validation includes all eight actual scenario entry files (strict scan),
the cached pinned nanoGPT train/model/configurator files (explicit profile),
new network rejection under that profile, immutable-configurator tampering,
uppercase Python extensions, pathlib reads and oversized integer literals.

Current focused offline result: **86 passed**, Ruff clean. This includes the actual
s1 tuple/conditional depth reduction, which is rejected as MODEL_SHRUNK, and
--steps truncation. The independent reviewer reproduced both pathlib-read and
large-integer fixes. The new pinned nanoGPT profile was covered by local tests;
its integration and independent review remain the root task's responsibility.

The reviewed nanoGPT cache fallback has exactly the same three fixed hashes and
rejects symlink directories/files. A caller cannot select an arbitrary baseline
path. Repository preparation publishes that cache atomically without overwriting
existing entries; patched candidates still compare unsafe AST operations against
the fixed original contents.
