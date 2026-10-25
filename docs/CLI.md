# CLI project configuration

`headroom fix` accepts a script, a local repository plus a Python launch command,
or a pinned public GitHub repository. These are existing repair workflows; this
document describes input configuration, not evidence of a completed live repair.

## Script and policy controls

```sh
headroom fix ./train.py --target fix-oom \
  --no-allow-numerics-change --no-allow-batch-grad-accum \
  --max-throughput-regression-pct 0 --max-steps 20 -- --batch 8
```

- `--search-mode until_target|bounded_pareto`: default `until_target`; explicit bounded exploration keeps the same maximum of six rounds and all existing budget, timeout and policy checks. It does not grant numerical-change permission.
- `--reclaim-reduction-pct`: target reduction for `reclaim`, default 30; strictly greater than 0 and at most 100.
- `--allow-numerics-change / --no-allow-numerics-change`: default false.
- `--allow-batch-grad-accum / --no-allow-batch-grad-accum`: default true.
- `--max-throughput-regression-pct`: default 25, accepted range 0–1000 percent.
- Arguments after `--` are literal target-script argv. Nonempty CLI target argv
  replaces the YAML `script_args` list as a whole.

The existing `--budget`, `--daily-budget`, `--runtime-profile` and `--research`
controls remain CLI controls; a project file cannot set them.

Run-budget interpretation comes from the explicitly selected reviewed runtime
profile. Its optional run_budget_mode defaults to strict_reservation.
actual_usage keeps the --budget 0.6 value as an actual-cost stop line while
requiring full provider-bound reservations in the shared authorized and daily
pools. It rejects local estimates. A single request can cross the run line;
that run stops with a partial report and fails its cost requirement. Equality
stops further calls but does not itself fail the cost <= limit check. Unknown,
pending or invalid billing also prevents an overall success claim while keeping
the earlier candidate's verification facts. A run crossing UTC midnight must be
restarted as a new run before any further model request.
See [runtime accounting](RUNTIME.md#explicit-actual-usage-run-stop-mode).
No new profile, credential, or spending authorization is created by this option.

## Local repository command

```sh
headroom fix --source-root ./my-project \
  --cmd 'python -u -W ignore -m package.train --batch 8' --target fit:16GB
```

The source root must exist. The entrypoint must resolve to supported Python
source inside it. The original Python flags, module form, and argument boundaries
are preserved in the Lab and candidate verification. Headroom locates editable
source without importing it on the host. Unsupported interpreters, entrypoints,
or options fail before repair dispatch. For an ordinary file:

```sh
headroom fix --source-root ./my-project --cmd 'python -u train.py --batch 8'
```

Do not combine `--cmd` with a positional script or extra target argv: place all
target arguments in the quoted command. Remote mode still requires
`--repo https://github.com/OWNER/REPOSITORY --ref COMMIT_SHA --cmd 'python ...'`;
the ref must be an exact lowercase 40-character SHA. Both repository command
modes use the original plan's repository acceptance scope; ordinary positional
scripts keep standard acceptance. YAML cannot choose this scope.

## Optional headroom.yaml

Use `--config ./project/headroom.yaml` to select an explicit file. Otherwise
Headroom checks, in order according to the selected input:

1. The explicit local `--source-root/headroom.yaml`.
2. The positional script's parent directory.
3. The current directory if no script or source root was supplied.

There is no parent-directory search. Remote repository mode does not
automatically consume a YAML file from the caller's directory or the fetched
repository. An explicit `--config` may still supply repair controls for remote
mode; the explicit command supplies its script and argv.

```yaml
version: 1
script: train.py
script_args: ["--batch", "8"]
target: fit:16GB
reclaim_reduction_pct: 30
policy:
  allow_numerics_change: false
  allow_model_change: false
  allow_batch_grad_accum: true
  max_throughput_regression_pct: 25
max_steps: 20
max_seconds: 120
seed: 1337
device: cuda
max_rounds: 6
search_mode: until_target
batch:
  arg: --batch
  value: 8
```

Run `headroom fix --config ./project/headroom.yaml`, or run `headroom fix` from
that directory. A configured script is relative to the configuration directory
and must remain inside it; when it selects the script, that directory becomes
the default source root. An explicit positional script replaces YAML `script`.
An explicit local or remote command replaces both YAML `script` and
`script_args`.

Precedence is **explicit CLI > YAML > existing defaults**. Explicit false,
zero and default-valued CLI options are preserved; for example
`--seed 0 --max-throughput-regression-pct 0 --no-allow-numerics-change` overrides
the corresponding YAML settings.

Supported fields:

| Field | Values / bound |
| --- | --- |
| `version` | integer 1; optional for legacy files |
| `script` | relative script path inside the configuration directory |
| `script_args` | list of at most 100 literal strings |
| `target` | existing `fix-oom`, `fit:<size>GB`, `reclaim` targets |
| `reclaim_reduction_pct` | numeric > 0 and <= 100; default 30; used with `reclaim` |
| `policy` | the four existing policy fields shown above; booleans must be YAML booleans |
| `allocator_conf` | allowlisted allocator configuration string, or null |
| `numerical_reference` | explicit bounded reference settings described below |
| `max_steps` | integer 1–10000 |
| `max_seconds` | integer 1–3600 |
| `seed` | integer 0–4294967295 |
| `device` | `cuda` or `cpu` |
| `max_rounds` | integer 1–6 |
| `search_mode` | `until_target` (default) or `bounded_pareto` |
| `batch`, `batch_arg` | existing static small-batch reference metadata |

Legacy `batch: {arg: --batch_size, value: 32}` and
`batch_arg: --batch-size` with optional positive integer `batch: 32` remain
supported. Allowed batch flags are `--batch`, `--batch_size`, and `--batch-size`.
These fields describe reference discovery; they do not inject target argv.
Reference discovery continues to inspect the script's adjacent `headroom.yaml`
and argparse, as before.

Files must be regular non-symlink YAML mappings no larger than 16 KiB. Unknown
fields, duplicate mapping keys, unsafe YAML tags, invalid types and out-of-range
values fail before dispatch. Errors do not echo file contents. This file cannot
store authentication, provider settings, runtime profiles, budgets, spending
authorization, research/live enablement, or acceptance-scope overrides. It does
not bypass any existing access, budget, Lab or verification checks.

## Offline validation evidence

The implementation is covered by request-capture CLI tests, bounded-file and
schema tests, legacy reference-discovery checks, and an in-process API
repository-command test. These use offline fixtures and do not prove a paid
model repair or CUDA acceptance. See the saved receipt under
`reports/project-config-20261024/`.

## Explicit bounded Pareto exploration

```sh
headroom fix ./train.py --search-mode bounded_pareto --max-rounds 6
headroom fix ./train.py --target reclaim --search-mode bounded_pareto
headroom watch --source-root ./my-project --search-mode bounded_pareto -- python train.py
```

Reclaim uses the existing `fix --target reclaim` entrypoint. `until_target` keeps
the existing target-reached stop behavior. `bounded_pareto` can continue after
first reaching the target, subject to the same run limits; it does not guarantee
two rounds, two non-dominated configurations, or a bf16 candidate. A permission
for numerical changes must still be supplied separately. Both modes retain
first-target and stop evidence; a later budget/timeout/error is not rewritten as
a successful terminal state merely because an earlier configuration met target.

For `fix`, explicit `--search-mode` overrides `headroom.yaml`, including an
explicit `until_target` override of YAML `bounded_pareto`. Missing configuration
keeps `until_target`. Invalid values fail before source preparation or dispatch.

`watch` also accepts `--config PATH`, otherwise checking the selected source
root's `headroom.yaml` (the working directory when no root was supplied). It
reads `search_mode`, `allocator_conf` and `numerical_reference` from that project
configuration; other Watch options retain their existing CLI/default behavior.
Explicit Watch `--search-mode` and `--allocator-conf` override their YAML values. The config is still validated as the same strict
ProjectConfig schema. `watch.json` records the requested mode even if no OOM
triggers repair. Historical reports without this field remain unknown.

`headroom eval --plan-only --search-mode bounded_pareto` plans the campaign
without executing it. Evaluation uses its own manifest's `search_mode`, not
`headroom.yaml`; see [EVALUATION.md](EVALUATION.md). No mode selection enables a
live profile or expands spending authorization.

## Explicit allocator and numerical reference settings

`headroom fix --allocator-conf 'expandable_segments:True'` applies an allowlisted
allocator setting to the baseline and subsequent verification. An explicit empty
string clears the project setting. Arbitrary environment variables cannot be
injected through this option.

The default reference strategy remains `legacy_small_batch`. Supported
original-workload references require an explicit choice; they retain their own
source, runtime and numerical qualification checks:

| CLI option | Meaning |
| --- | --- |
| `--reference-strategy` | `legacy_small_batch`, `original_saved_tensor_offload`, or `original_workload_checkpoint` |
| `--reference-cpu-bytes` | Saved-tensor CPU cap, 1 byte through 16 GiB; default 16 GiB |
| `--reference-disk-bytes` | Saved-tensor disk cap, 0 through 64 GiB; default 0 disables disk storage |
| `--reference-max-seconds` | 1 through 480 seconds, or CLI 0 for the normal Lab timeout; the outer run deadline still applies |

The equivalent YAML/API/evaluation object is:

```yaml
numerical_reference:
  strategy: original_saved_tensor_offload
  cpu_saved_tensor_limit_bytes: 17179869184
  disk_saved_tensor_limit_bytes: 68719476736
  max_seconds: 480
```

The object rejects unknown fields. YAML `max_seconds` uses null, not 0, for the
normal timeout. Legacy small-batch references reject nondefault resource limits;
checkpoint references accept a timeout but reject offload resource overrides.
Explicit CLI values, including defaults and 0, override YAML values. Watch takes
the reference object from its project configuration and records it in watch.json.

These settings select verification methods; they do not grant precision changes,
change acceptance scope, provide credentials or increase any spending limit.
See [verification contracts](VERIFY.md) for supported source patterns and failure
semantics.
