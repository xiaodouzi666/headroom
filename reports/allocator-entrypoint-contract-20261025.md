# Initial allocator and reference entrypoint audit — 2026-10-25

The numerical-reference integration review found one concrete regression:
`watch` always supplied `numerical_reference`, but `watch_command` rejected that
field before baseline execution because its fix-option allowlist lacked it.
The allowlist now includes this explicit bounded model. Defaults remain legacy;
this does not enable offload for old configurations.

The initial `allocator_conf` setting now travels through project YAML, CLI,
installed CLI evaluation, scenario manifests, API admission and Watch. Every
public declaration model uses the existing `lab.envs.validate_allocator`
allowlist before execution. This is one supported allocator setting, not a
facility to inject arbitrary environment variables.

- Missing/null settings preserve the existing default. YAML, API and manifest
  empty strings remain invalid.
- CLI `--allocator-conf ''` is an explicit reset to null. The installed CLI
  always emits the option, including that reset, so ambient project YAML cannot
  change the manifest's declared baseline environment.
- `campaign_plan`, campaign result rows, API queue metadata and `watch.json`
  record the initial choice. Scenario values reach the actual `FixRequest`.
- The original baseline already used `request.allocator_conf`; current candidates
  inherit it unless a separately validated patch proposes an allocator change.
  Numerical references retain the original baseline setting. Watch's first
  `run_argv` also uses the same setting before any repair is triggered.

The independent reference integration review confirmed that legacy references
are cached only under the legacy strategy. Explicit offload receives no cached
reference and must run its own existing source-bound proof. The evaluation
supervisor still owns a single 480-second deadline; no new clock or extension was
introduced. Reference options are carried by the full validated request, and old
saved scores are not recalculated.

New tests exercise strict allowlist/type rejection, arbitrary-env rejection,
null and YAML precedence, actual CLI-to-Watch baseline and repair dispatch,
API preparation and queue persistence, manifest-to-request/result transport,
and original-baseline/candidate/reference allocator arguments. Mocked GPU/provider
boundaries are explicitly offline; no live model or GPU was used for these tests.


Final entrypoint/config/API/Watch-command focused validation: **331 passed in
62.13 seconds**. The final diagnosis/orchestrator/Watch unit selection passed
**73 tests**, with 12 real-CPU-Docker/timeout selections excluded from that narrow
run; the existing API deadline suite was included in the 331-test run. Ruff and
`git diff --check` passed. The broader final regression remains root-owned.
