# Command-mode repair

The command path implements the execution handoff in PLAN C.3, T1.9 and the mapped-Python wrapper path in T2.6.
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

## Shell and executable wrappers

Watch can repair a wrapper with one observed, mapped Python entrypoint, for example:

```sh
headroom watch --source-root /absolute/project -- /bin/sh launch.sh --batch=8
headroom watch --source-root /absolute/project -- /bin/sh -c 'cd sub && exec python -O -m pkg.train --batch=8'
headroom watch --source-root /absolute/project -- ./launch.sh --batch=8
```

The entire launcher argv is replayed unchanged inside Docker. sitecustomize
records the Python process's startup cwd, original interpreter argv, initial
and effective target argv, main source file, module spec and process identity.
The host checks the source mapping against the captured file manifest.
Relative cwd and package imports remain part of the invocation.

A candidate or small-batch reference can change target arguments without
rewriting the shell program. Lab passes an internal target-argv override;
sitecustomize applies it before the Python main only when startup cwd, complete
original Python argv and original target arguments all match the captured
descriptor. Interpreter flags, `-m`, and the wrapper remain unchanged. Other
Python launches do not match and are not modified. The result records whether
the override matched/applied and what arguments actually entered the main.
A missing match, changed entrypoint, or multiple observed Python capture owners
cannot pass replay verification.

`FixRequest.execution_entrypoint` carries this captured descriptor. It cannot
be inferred from an arbitrary shell string at source-preparation time:
use Watch to obtain runtime evidence. Existing direct-Python `fix --cmd`
entrypoints keep their original behavior. Non-OOM wrapper exit codes are
preserved, including nonzero SystemExit.

## Reproducing a kept wrapper configuration

The kept configuration's `manifest.json` saves the original wrapper command
and `execution_entrypoint`; `cli.json` saves original/effective target args.
Together they are the Lab replay contract. Given a source tree with the patch
applied, call `run_script` with its mapped Python file, that source root, the
saved `execution_argv`, saved descriptor, and `cli.json["effective"]` as
`script_args`. Lab reinjects and verifies the targeted override.

`git apply` applies source edits only. A normal external shell invocation does
**not** consume Headroom's saved descriptor or apply its target-argv override.
To run outside Lab, the user must also implement the saved target-argument
changes in their launcher/configuration and apply any recorded environment
changes. The report must not suggest that applying the source diff alone
reproduces CLI changes.

## Explicit remaining limits

- `-E`, `-I` and `-S` disable the configured injection path.
- Inline `-c`, stdin or non-Python runtimes without a source-backed Python main
  cannot be mapped to an editable repair target.
- Multiple observed Python entrypoints are reported as ambiguous; one primary
  process is not silently treated as a complete distributed workload.
- Module/source/cwd must resolve inside the copied source. Runtime capture is
  observed process data, not authentication against deliberately falsified code
  or proof that no uninstrumented process existed.
- Interactive stdin/TTY forwarding and dependency installation remain unsupported.

## Reproduction

```sh
.venv/bin/python reports/wrapper-replay-20261024/run_tests.py
```

The script installs a network-denial guard before importing pytest, uses the
existing local tiktoken cache and hides host CUDA devices. Real execution tests
select CPU Docker explicitly. OOM-to-fix tests use labelled synthetic captures;
they do not manufacture GPU acceptance evidence.
