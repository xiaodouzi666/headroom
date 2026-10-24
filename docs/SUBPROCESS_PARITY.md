# T2.7 independent subprocess comparison

The original PLAN C.3 allows a subprocess or Docker sandbox, and explicitly names
both runpy and subprocess + sitecustomize capture. T2.7 requires three scenarios
whose Docker/subprocess results agree within 1% CUDA peak allocated memory.
It does not require running untrusted targets directly on the host.

The historical user/network namespace probes remain failed (uid_map EPERM and
bwrap loopback EPERM). This implementation does not alter AppArmor, seccomp,
sudo policy, services or that historical record. It uses the existing Docker
boundary around a separate subprocess controller. It does not claim
that the bare-host subprocess backend now works.

## Distinct execution paths

- Production: headroom.lab.runner.run_script → production docker.execute →
  headroom.lab.run_target → runpy + capture hooks.
- Reference: the acceptance launcher independently creates/starts/inspects/kills/
  removes a boundary container. Its trusted subprocess_reference controller
  starts a new Python process/session with subprocess.Popen; only that child
  gets sitecustomize and the original capture hooks. The controller does not
  import torch and is not counted as a captured training process.

The reference does not call production _run, run_script, run_command or
docker.execute. Both arms intentionally share immutable image validation,
the isolation argv constructor, reviewed HF cache validation, bounded source
copy, the same GPU lock, environment whitelist, monotonic clock contract and
capture implementation. These shared primitives keep the measurement and safety
definitions equal; this comparison cannot independently prove those shared
primitives correct.

Both containers retain network none, read-only root/source/runtime/control,
unprivileged uid, all capabilities dropped, no-new-privileges, memory/CPU/PID
limits and only the approved output/tmp/cache mounts. No host venv, credential
file, Docker socket, privileged mode or extra host execution path is added.

## Deadline, exit and evidence

The reference publishes one read-only monotonic deadline immediately before
container start, including startup in the execution duration. The child capture
uses the unchanged soft collection window; the controller and host share the
same hard deadline and never start a fresh timer for the child. Container
creation is separately bounded by 30 seconds, as in the production path.
Cleanup/inspection can take additional bounded time after execution stops;
the command is not promised to return within the execution duration.

The child starts a new process group. The controller drains bounded stdout/stderr,
preserves the actual child exit code, terminates/reaps that group, and records
its result separately from the child's raw capture. The outer host controller
always removes the whole named container, including escaped descendants.
Missing/incomplete capture, unexpected exit, cleanup uncertainty or timeout
cannot pass acceptance. A controlled sitecustomize step-limit exit (code 1)
is accepted only when the recorded capture explicitly says completed/step_limit.
An arbitrary nonzero exit stays an error.

Each run retains source hashes, exact request/argv/environment, immutable image
identity, deadline, controller PID/child PID/exit, raw capture, bounded child logs,
container state and cleanup evidence. Result JSON does not authenticate arbitrary
target-generated files; the acceptance cases are pinned, reviewed source scripts.

## Commands

Default inspection is read-only and does not execute targets:

    source scripts/env.sh
    uv run --offline python scripts/check_docker_subprocess_parity.py

After the root operator has an idle GPU window, explicitly execute the three
pinned cases (s1 OOM, s3 normal completion, HF Trainer OOM), with two arms each:

    uv run --offline python scripts/check_docker_subprocess_parity.py \
      --execute --output runs/t2.7-independent-subprocess-UNIQUE \
      --max-seconds 180

The output directory must be new. The shared GPU lock and pre-run observation
refuse a busy GPU. Every arm uses max_steps=20 and seed=1337. Expected OOM cases
retain their observed failure step count; they are not forced to complete 20
updates. The source pins and expected statuses come from the existing canonical
scenarios. No model calls are involved; Token Factory/Tavily cost is zero.

The report retains all pairs, including failures. Per-case acceptance requires
matching nonempty source manifests and the frozen script SHA, image/capture
configuration, status, step/loss/parameter observations, complete capture,
confirmed cleanup and complete GPU samples with no observed sharing, plus

    100 * abs(peak_production - peak_reference) / peak_production <= 1

using positive integer CUDA byte peaks and Decimal arithmetic. GPU point samples
do not prove continuous exclusivity; no throughput acceptance is claimed. Overall T2.7
requires all three CUDA pairs. No rounded percentages, CPU samples or historical
baseline-only records substitute for that gate.

## Validation boundary

tests/test_subprocess_reference.py independently blocks DNS/INET and credential
reads on the test host. Real containers use CPU and network none: SGD, AdamW and
HF Trainer paired runs; read-only source/runtime/control/root/HF cache and
network/secret isolation; ignored-signal hard timeout; nonzero exit preservation;
and background process-group cleanup. Tests also prove the reference arm can
execute while production dispatch functions are disabled.

CPU parity never sets t2_7_case_accepted. No real CUDA pair has been executed by
the implementation task; the original T2.7 acceptance remains pending until the
explicit six-arm command is run and all three recorded results pass.
