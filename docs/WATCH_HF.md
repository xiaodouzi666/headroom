# Watch, offline Trainer, and HF cache

Implementation and CPU evidence are available. The original T2.5 repair gate and
T2.7 CUDA peak equivalence gate remain pending; no tiny CPU result is a substitute.
No Nebius/Tavily calls or model-key reads were needed for this implementation.

## Watch API for CLI integration

```python
from headroom.watch import watch_command

result = watch_command(
    ["python", "train.py", "--batch=16"],
    source_root="/absolute/reviewed/source",
    device="cuda",
    max_steps=20,
    max_seconds=120,
    seed=1337,
    fix_options={"budget_usd": "0.6", "target": "fix-oom"},
)
# Display preserved stdout_path/stderr_path and watch_report_path/report_path.
# CLI returns result["exit_code"].
```

Watch accepts a nonempty argv sequence (up to 256 entries / 64 KiB). It never
implicitly joins arguments into a shell string. Python aliases resolve to the
container's mounted virtual environment; all other executables resolve only in
the Docker image or copied source. Explicit commands such as
`["/bin/sh", "-c", "python train.py"]` execute that shell **inside Docker**.
`python -m package.entry`, inline `-c` programs, interpreter options, module/package
relative imports and literal shell-looking argv are preserved during observation.
No host binary, source, shell or package setup is executed as a fallback.

Automatic repair supports direct Python scripts and local `-m` modules/packages
inside the captured source. Interpreter options such as `-O`, `-W`, `-X` and
`-x` are retained through baseline, candidate and reference execution via the
same sitecustomize command backend. The editable source path does not replace
the original module invocation. Inline code, generic/shell launchers and
distributed commands remain capture-only: a confirmed CUDA OOM returns
`needs_human`, its original exit code and evidence. See
[COMMAND_MODE.md](COMMAND_MODE.md) for the complete replay contract and limits.

Options `-E`, `-I` and `-S` can prevent sitecustomize capture. Non-Python runtimes
may also produce no allocator evidence. Such runs retain the real container exit
and logs, mark `capture_status=unknown`, and return `needs_human`; stderr containing
"CUDA out of memory" is never treated as authoritative OOM evidence. Interactive
stdin/TTY forwarding is not implemented. Distributed/multi-process launchers are
observation-only: a single captured process is not a verified aggregate memory
profile or a safely replayable repair command.

Every observed command uses Lab's no-network, read-only-source Docker container,
secret-free environment, process/time/step bounds and verified cleanup. No
watched source is imported or executed by the host interpreter. A normal command
exit, including `SystemExit(7)`, is returned unchanged. Timeout returns 124;
infrastructure or uncertain-cleanup failure returns 125. Controlled step capture
is marked `capture_limit`; its original command exit is retained (normally 1).
Thus a bounded observation is not misreported as the original command finishing.
Logs are retained with Lab's existing 8 MiB per-stream limit; current Python API
returns their paths after observation rather than implementing live terminal I/O.

Only a complete Lab CUDA OOM result, consistent non-running container state,
non-cgroup OOM, confirmed cleanup and a supported repair entrypoint triggers `run_fix`. CPU OOM, a printed OOM
message, arbitrary nonzero exit, timeout, incomplete capture and host-memory
cgroup OOM never trigger repair. The repair uses the failing Lab source snapshot,
not an original directory that may have changed during observation. The existing
orchestrator performs its normal preflight, baseline, policy, model and budget
checks. Unconfigured model access can produce `needs_human` and its partial
report. A returned completed repair changes Watch exit to 0 only when
`target_met is True`; an unverified repair preserves the original OOM exit.

Results include `watch_id`, `run_dir`, `status`, `exit_code`, `original_exit_code`,
`triggered`, `lab`, `fix`, `stdout_path`, `stderr_path`, `report_path` and
`watch_report_path`, `command_details`, `repair_supported`,
`repair_unavailable_reason`, `capture_status` and `cuda_oom_confirmed`. Each observation retains `watch.json`, `watch.md`, the Lab
run and any full repair under separate directories. The callable injection seams
`lab_runner`/`fix_runner` are trusted offline test seams, not request fields.
Raw source-written evidence remains subject to Lab's existing non-authentication
limitation; static checks plus sandboxing are not a proof of honest target code.

## HF Trainer fixture

`repos/hf_trainer.yaml` points to `repos/hf_trainer/train.py`. Its default command
`python train.py` constructs a **randomly initialized** GPT-2 model with
24 layers, 16 heads, width 1024, vocabulary 50,257 and sequence length 1024.
Trainer starts at per-device batch 16, FP32 AdamW, no gradient checkpointing and
one accumulation step. Fixed synthetic tokens and model/data seeds use 1337.
No model weights, tokenizer, dataset, remote code or Hub account is downloaded.
Pinned dependencies are Transformers 4.46.3 and Accelerate 1.1.1 with Torch 2.5.1.

TrainingArguments are the intended small patch surface: per-device batch,
accumulation, gradient checkpointing, and policy-permitted BF16. Model size,
sequence length and training length must not be reduced to claim success.
The original acceptance still requires `target_met=true`, a configuration-only
patch of at most 15 changed lines, and a diagnosis identifying optimizer state
plus activations. The metadata's expected categories describe the intended
scenario, not observed allocations or a verified diagnosis. BF16 is unavailable
under the default `allow_numerics_change=False` policy.

`python train.py --profile cpu-smoke --device cpu` selects an explicitly different
2-layer, 2-head, width-32 model with vocabulary 128 and sequence 32. It has 30,592
parameters and is only an implementation test. Trainer's output is under `/tmp`,
checkpoint saving and external reporting are disabled, and data-loader workers
are zero. Source stays read-only. `headroom.yaml` exposes `--batch_size` for the
original small-batch-reference discovery; unknown pairing evidence still yields
`loss_equivalence=n/a` and does not waive the original numerical gate.

## Offline cache boundary

Lab always sets `HF_HOME=/tmp/headroom-hf`, hub/data cache subdirectories below it,
`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_DATASETS_OFFLINE=1`, disables Hub
telemetry and tokenizer worker parallelism. Host HOME, HF tokens, arbitrary host
cache locations and host environment overrides are not inherited. Temporary
cache writes disappear with the container; cache misses fail offline.

The host environment in scripts/env.sh uses .cache/huggingface as its mutable
HF_HOME Hub/account cache. Hugging Face libraries may create hub/version.txt
there during import. That host cache is never selected or mounted into Lab.

An optional **operator-reviewed**, project-owned .cache/hf-reviewed directory
can be mounted read-only at /hf-cache. It is never automatically created or
filled. It must contain manifest.json with this shape:

```json
{"schema_version":1,"files":{"random-model/config.json":"<sha256 of bytes>"}}
```

All files must be listed and hash-matched, regular data leaves within 8 GiB and
10,000 entries. Supported names are model/config/tokenizer data (including
safetensors shards); pickles, Python code, tokens, unlisted files and all symlinks
are rejected. This is a staged local model directory, not the logged-in Hugging
Face cache format. Use explicit local paths such as
`GPT2Config.from_pretrained('/hf-cache/random-model', local_files_only=True)`.
Keep the reviewed directory immutable during jobs. The manifest verifies data
integrity, not the provenance or semantics of a model. A corrupt existing cache
fails preparation rather than silently using different files or going online.
The former shared .cache/huggingface path is no longer a reviewed mount source.
Existing host data stays untouched. Operators who previously staged reviewed
data there must explicitly stage and review it under .cache/hf-reviewed before
requesting /hf-cache paths; there is no automatic migration or fallback.

## Verification evidence and unchanged limits

`tests/test_watch.py` covers unsupported commands, OOM-only dispatch, captured
source handoff, safe partial failure, cleanup uncertainty and actual CPU Docker
exit preservation. Model calls are injected fakes, never live.

`tests/test_hf_cache.py` tests token/unlisted-file, hash, missing-file, symlink and
pickle rejection; a real CPU Docker process reads a synthetic local HF config,
cannot modify its read-only mount, can write its temporary HF directory and
fails on an unavailable local-only model.

`tests/test_hf_trainer.py` runs three CPU scenarios (SGD, AdamW and Trainer) through
both `run_script` wrapper and `run_command` injected capture. Loss sequences and
parameter counts match exactly; all containers are cleaned. Trainer completes
20 steps, the two simple scenarios complete 4. Both paths remain Docker-isolated.
The current saved evidence is under `runs/watch-hf-tests-20261024-b`, with
`cpu-parity.json` per scenario; that run passed 63 tests including existing Docker
boundary regressions. Subsequent focused checks are recorded below.

These CPU checks do **not** satisfy T2.7's three-scenario CUDA peak delta ≤1%
between Docker and subprocess paths. No untrusted host subprocess was enabled.
Public/live-model repair, a <=15-line model-generated HF repair, and the full
Watch CUDA OOM-to-repair flow remain pending the appropriate live credentials
and original evidence requirements.
Full CUDA baseline on 2026-10-24: `reports/hf-trainer-baseline-20261024.json`
records a real OOM at default batch 16, 354,823,168 observed parameters,
24.805119488 GB peak allocated and 24.826085376 GB peak reserved. Capture was
complete, no shared GPU was observed, and cleanup was verified. It failed before
the first optimizer step, so optimizer-state allocation was not observed; the
expected two-category diagnosis has not been accepted. This baseline evidence
does not establish repair success. GPU was empty again after the run.

Final focused verification: 73 tests passed in 28.92 seconds under
`runs/watch-hf-tests-20261024-c`; Ruff passed. This includes the nanoGPT equals-argv
regression and the original CPU paired verification. The optional-cache test now
uses a unique UUID container name, so independent runs cannot reuse its name.


## T2.7 independent subprocess isolation preflight

`reports/t2.7-isolation-preflight-20261024.json` records the real lightweight
checks on azuki. `bwrap`, `unshare`, `prlimit` and `timeout` are installed; bwrap
is not setuid. The following trusted `/usr/bin/true` probes failed:

- `unshare --user --map-root-user -- /usr/bin/true`: exit 1,
  `write failed /proc/self/uid_map: Operation not permitted`.
- The same command with `--net`: the same exit and uid-map error.
- `bwrap --unshare-all --die-with-parent --new-session`, with only read-only
  runtime directories, proc/dev/tmp mounts and `/usr/bin/true`: exit 1,
  `loopback: Failed RTM_NEWADDR: Operation not permitted`.

No sudo, installation, system change, GPU workload or host training process was
used in these probes. With these permissions, the required independent restricted
subprocess path cannot be established. This is an environment blocker independent
of Nebius account access. The original three-scenario CUDA peak delta <=1% gate
remains unmet; two Docker capture entrypoints cannot prove that gate. No unsafe
host execution path was enabled, and no redundant full GPU baselines were run.


## General argv Watch verification

Final targeted run `runs/watch-argv-final-20261024-a`: **89 passed in 15.79
seconds**, Ruff clean. The suite includes original repository/parser and Docker
boundary regressions plus actual CPU Docker commands exercising module-relative
imports, multiline `-c`, `-O`, capture-disabling `-I`/`-S`, a container shell,
literal shell-looking argv and nonzero exits. A paired CPU check confirms that
supported `-uBs` effects and script argv match the existing repair Lab environment.

The `run_argv` helper always delegates to Docker; the existing `run_command`
Python-only API and strict repository parser remain compatible. Watch's callable
signature is unchanged. JSON reports now record the original command classification,
interpreter flags, repair eligibility/reason, capture availability and whether
CUDA OOM was confirmed. No stderr heuristic upgrades missing capture into OOM.
Model repair dispatch tests use injected fakes; no live API was called and no
GPU baseline was repeated in this extension. The original end-to-end repair gate
remains separate from these command-observation tests. Non-script automatic
repair still requires a replayable entrypoint supported by the fixer; it is not
silently claimed complete by successful observation.


## Host cache collision correction (2026-10-24)

The complete continuation suite retained 18 CPU Lab failures because ordinary
HF_HOME Hub metadata had created .cache/huggingface without a reviewed manifest.
This was a production configuration collision as well as a test failure: Docker
preparation validated that directory even for workloads not using HF models.
The reviewed mount now uses the separate .cache/hf-reviewed path. No existing
cache data, manifest or model weights were moved, rewritten or downloaded.
Manifest/schema/hash/type/symlink limits remain unchanged.

After sourcing scripts/env.sh, the scoped cache/runner/verify/watch rerun reports
64 passed in 67.77 seconds, including the previously failing CPU cases and new
host-versus-reviewed cache separation checks. Its complete log is preserved in
reports/cache-path-separation-20261024/tests.log. The SSH connection disconnected
while returning output, so the receipt records that transport failure separately
from the completed pytest log. No GPU or model API acceptance is implied.
