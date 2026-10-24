# Command-mode repair

The command path implements the execution handoff in PLAN C.3 and T1.9.
CPU Docker checks and offline OOM handoff fixtures exercise the implementation;
they do not certify a GPU OOM repair, model diagnosis, numerical equivalence,
or the full arbitrary-command requirement in T2.6.

## Entry points

`headroom fix --source-root /absolute/project --cmd 'python -O -m pkg.train --batch=8'`
and `--repo URL --ref COMMIT --cmd 'python -W ignore train.py --batch=8'` retain
the Python invocation. Watch uses the same parser after capture:
`headroom watch --source-root /absolute/project -- python -O -m pkg.train --batch=8`.

`prepare_local_command(source_root, command)` returns the editable `script`,
`source_root`, target-only `script_args`, and full `execution_argv`.
`FixRequest.execution_argv` is optional; absent preserves the existing script
wrapper behavior. A command request must agree with the resolved editable file
and original target arguments. Source lookup uses local files only: no host
import, package installation, user setup, or model call occurs.

Direct Python scripts, `/source/path.py`, normal local modules and package
`__main__.py` entrypoints are supported. Interpreter options such as `-O`,
`-OO`, `-W`, `-X`, `-u`, `-B`, `-s`, and `-x` remain in the invocation.
The executable alias is normalized to Lab's mounted Python; all other argv
tokens, quoting boundaries, module invocation and interpreter options remain.
Shell-looking target arguments are literal argv, not host shell syntax.

## Baseline, candidate and reference

`run_script(..., execution_argv=command)` selects the existing `run_argv`
Docker backend and sitecustomize injection. Every replay uses the unchanged
interpreter/entrypoint prefix plus the current target arguments. This includes
small-batch references, where only the target batch argument is changed. A
module is never converted to `runpy.run_path`: package-relative imports,
`__package__` and module search behavior remain those of the original command.
All invocations start in the existing `/source` container working directory.

Watch repairs the captured source copy. The evidence builder resolves flagged
script/module commands with the same parser and includes local package
initializers and imported source when present. Source hashes still come from
the captured manifest. Reports retain the original request argv; kept
configuration manifests retain original and effective full argv, in addition
to the existing target-only `cli.json`. Repository preparation records
requested and executed argv, including the reviewed nanoGPT dataset rewrite.

`repository_mode=True` is set only by explicit repository-command entrypoints;
ordinary Watch does not inherit the T1.9 no-reference exception. This flag does
not certify that numerical equivalence was measured. All source/policy,
runtime, billing and verification gates remain in the production flow.

## Explicit remaining limits

- `-E`, `-I`, and `-S` disable the configured injection path and cannot
  enter automatic repair. They can still be observed with their real exit.
- Inline `-c`, stdin, shell wrappers, arbitrary binaries and distributed
  launchers remain capture-only. A shell may launch a captured Python child,
  but the current capture protocol lacks a reliable mapping from that child's
  main file/cwd to a replayable repair target. Such OOMs retain evidence and
  return `needs_human`; no synthetic source file or altered launcher is used.
- Module source must resolve inside the copied source tree. Installed-only
  modules and dynamic import-path launchers need explicit source/entrypoint
  support. Static source lookup is not proof of the behavior of custom import
  hooks or deliberately falsified capture data.
- No interactive stdin/TTY forwarding or dependency installation is added.

The next step for shell-wrapper repair is to capture the actual Python main
file, module spec, original argv and cwd in the owning process, validate its
mapping to the captured source manifest, then replay the unchanged root
launcher. Multiple Python workers require an explicit aggregation/selection
contract. This is still pending; Python command repair does not imply that
all arbitrary commands can now be repaired.

## Reproduction

```sh
.venv/bin/python reports/command-replay-20261024/run_tests.py
```

The script installs a network-denial guard before importing pytest, uses the
existing local tiktoken cache and hides host CUDA devices. Real execution tests
select CPU Docker explicitly. OOM-to-fix tests use labelled synthetic captures;
they do not manufacture GPU acceptance evidence.
