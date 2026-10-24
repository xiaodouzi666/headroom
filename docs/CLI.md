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
