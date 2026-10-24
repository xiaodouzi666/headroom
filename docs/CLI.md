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
reads **only `search_mode`** from that project configuration; all other Watch
options retain their existing CLI/default behavior. An explicit Watch
`--search-mode` overrides YAML. The config is still validated as the same strict
ProjectConfig schema. `watch.json` records the requested mode even if no OOM
triggers repair. Historical reports without this field remain unknown.

`headroom eval --plan-only --search-mode bounded_pareto` plans the campaign
without executing it. Evaluation uses its own manifest's `search_mode`, not
`headroom.yaml`; see [EVALUATION.md](EVALUATION.md). No mode selection enables a
live profile or expands spending authorization.
