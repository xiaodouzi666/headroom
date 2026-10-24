# Lab capture

The Lab runs target Python code in Docker and saves measured execution artifacts.
It does not diagnose or repair a model and does not call Nebius or Tavily.
All original T1.1 clauses passed the measured checks recorded in
`reports/t1.1-acceptance.json`. This acceptance covers capture and execution
boundaries; T1.2 evidence reconstruction and model diagnosis/repair remain pending.

## Script entry point

```sh
source scripts/env.sh
uv run headroom snapshot scenarios/s1_batch_too_big/train.py
uv run headroom snapshot scenarios/s3_eval_no_grad_missing/train.py --max-steps 20 --seed 1337 -- --batch 1 --steps 100 --seed 1337
```

Target arguments follow `--`. The wrapper records a scalar loss whenever the
script calls Tensor.backward, and counts actual optimizer steps using PyTorch's
global optimizer post-hook, including overridden AdamW.step. Reaching the step
limit is a controlled completed run. A regular exception, CPU OOM, capture failure
or container/record mismatch is an error. A genuine CUDA OOM is recorded as oom;
the snapshot command exits successfully when that evidence was captured correctly.
A host deadline produces timeout and the entire owned container is removed.

## Python command entry point

`headroom.lab.runner.run_command(source_root, ["python", "train.py", ...])` injects
capture through sitecustomize. It accepts Python argv, not a shell command string.
The production repair path also uses this command backend through
`run_script(..., execution_argv=command)`, retaining interpreter flags and
`-m` semantics across baseline/candidate/reference runs. See
[COMMAND_MODE.md](COMMAND_MODE.md).
Bootstrap failures terminate with an error instead of silently running without
capture. Descendant Python processes write separate process evidence. The host
checks the primary capture record against the actual container exit state.

Both entry points use an independent source copy. GPU calls share a project lock
and reject an already occupied GPU. GPU observations are samples before and after
execution and capture initialization, not continuous proof of exclusive use.

## Artifacts and units

Each run retains its source manifest, immutable Docker image ID, command, allowed
environment, stdout/stderr, container state, cleanup attempts and host result.json.
The artifacts directory contains the original container result and, for CUDA,
snapshot.pickle, snapshot.json, memory_stats.json, memory_summary.txt, environment
and traceback evidence. Existing runs are kept.

GB fields use bytes / 1,000,000,000; exact byte fields remain available. Peak
allocated/reserved counters are historical allocator maxima. The snapshot's
segments describe the capture instant; device_traces preserve allocation history.
Peak composition must not be inferred by pretending terminal blocks are peak
blocks. Evidence-pack reconstruction belongs to T1.2 and is not accepted here.

Raw pickle remains for PyTorch-compatible tooling. Host code reads only bounded
regular JSON files with no symlink following; it never unpickles target output.
Capture JSON is an observation produced in the target process, not authenticated
proof against deliberately falsified scripts. Later honesty validation remains
separate.

## Isolation

Containers have no network, a read-only root filesystem and source/dependency
mounts, no added capabilities, no-new-privileges, and CPU/RAM/PID limits. Only the
run artifacts directory and a bounded temporary filesystem are writable. Host
API credentials are not inherited. The runtime mounts only the headroom package,
not the project root containing .env. Source copying excludes credential files,
cache/run directories, special files and symlinks, and enforces size/count limits.

Weights/data requiring separate cache mounts are not yet implemented by this
entry point; those later repo/cache workflows remain pending. The caller must
prestage permitted inputs in its selected source tree within the copy limits.

## Verification

```sh
uv run pytest -q tests/test_runner.py tests/test_lab_docker.py tests/test_lab_hooks.py
uv run python scripts/verify_lab.py
```

The first command exercises CPU Docker boundaries, real AdamW truncation,
determinism, command capture, CPU OOM classification and a real 30-second timeout
with a child process. The second runs full-size s1 and two small-batch s3 GPU
captures, preserving every original T1.1 threshold, including more than 1000
s1 device-0 trace events. Failed checks remain failures in its JSON report.

## Measured T1.1 acceptance — 2026-10-23

`reports/t1.1-acceptance.json` combines the formal GPU report
`reports/lab-gpu-acceptance-20261023T022523Z.json` with the CPU integration/unit test log
`reports/lab-tests-20261023T0212.log`: **61 passed in 53.15 s**. All 13 GPU
checks are true. The GPU collector deliberately leaves `task_accepted=false`
because it cannot independently accept the CPU clauses; the combined acceptance
record closes those original T1.1 clauses without editing that raw report.

| Original clause | Measured result |
|---|---|
| s1 status | `oom`; complete capture and verified cleanup |
| s1 snapshot | Pickle exists (577,557 bytes); exported JSON has 2050 device-0 events, exceeding 1000 |
| s1 failed allocation | Allocator OOM event: requested 268,435,456 bytes = 0.268435456 GB > 0 |
| s1 traceback | Contains `OutOfMemoryError` |
| s3 small-batch completion | Batch 1, seed 1337; two runs each completed 20 optimizer steps and recorded 20 losses |
| Same-seed determinism | First five s3 losses exactly equal across both GPU runs |
| 30-second timeout | Real infinite loop and child process: TIMEOUT after 30.001734 s, owned container/children cleaned up |
| Credential isolation | Subprocess NEBIUS_API_KEY is null; TAVILY_API_KEY, HF_TOKEN and a canary key also null; source read-only |

Formal runs under `runs/lab-acceptance/20261023T022523Z/`:

| Case | Run ID | Capture wall s | Allocated peak bytes | Reserved peak bytes |
|---|---|---:|---:|---:|
| s1 | 48877b189d1040aba0cf39147f594f7f | 3.193099 | 24750424064 | 24752685056 |
| s3 a | 584cc1c4c2c04ba79954eaa22d471a0b | 5.589196 | 509994496 | 530579456 |
| s3 b | e9b2840fda8044329e1a1104ca68aa02 | 5.424451 | 509994496 | 530579456 |

The s3 first five losses are `[1.0982863903045654, 1.0958553552627563,
1.0934312343597412, 1.0910136699676514, 1.0886027812957764]`.
Each run's copied source hash matches its manifest and current train.py: s1
`668fe35db321d1738f42dd576f28f3efebf5b50693556dfdfec7f90c4f10ea28`; s3
`7fedcae13989b309cc5a034e62284094829057654aebb2e716c3413dfb0fea67`.
The wrapper sets max_steps 20 and seed 1337; target s3 asks for 100 steps, so
the measured 20-step completion exercises the optimizer hook limit.

The s1 fixture is width 256 / depth 192 with 101,007,360 parameters. Its
calibration from the old width 1024 / depth 12 fixture preserves batch, sequence,
optimizer and root cause but changes the model version. It is not a repair.
The standalone T0.6 baseline uses its own seed/timing and terminal counters;
do not compare it with these instrumented captures as an optimization result.

CPU artifacts are retained under
`runs/lab-test-history/20261023T0212-full/`, including the timeout
`56642d7265064c0899dbeda692ae11c3`, boundary check
`c92f18aac7284aba8359d87845d29783`, real AdamW, command capture and symbolizer
fixtures. JSON snapshots and pickle file existence/size were independently
checked without unpickling target output on the host.

## Full C++ symbolization dependency and preserved failures

The first GPU capture attempt failed while exporting a full-stack snapshot.
The original failure report
`reports/lab-gpu-acceptance-20261023T020307Z-failed.json` preserves all three
capture failures (`stoi`), rather than calling their training progress success.

PyTorch's full C++ symbolizer invokes addr2line and parses its line-number
output. In the pinned [PyTorch v2.5.1 unwind.cpp implementation](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/csrc/profiler/unwind/unwind.cpp#L395-L414),
the parser converts that result with std::stoi. Adding `binutils` supplies
addr2line in the Lab image; snapshot history and the >1000 threshold were retained.

| Environment | Immutable image ID | Minimal CPU-only `CapturedTraceback.extract(cpp=True).format()` |
|---|---|---|
| Old image | sha256:59d25199f7af74c53c6d24ba873eec4b0e76312a22dd3869dd873a51e4cbc804 | ValueError: stoi |
| New image | sha256:54accb9f005c435d13c018026781487600914cd99434a2d424136522dfed3661 | 17 frames |
| Host pinned environment | Host .venv, no container | 17 frames |

The independent minimal diagnostic mounted no GPU and no network in Docker,
used read-only dependencies, and confirmed CUDA stayed uninitialized in all
three environments. Its results are embedded in `reports/t1.1-acceptance.json`.
The separate wrapped regression-test fixture records 30 frames with CUDA
uninitialized; frame counts depend on the call stack, so these are distinct probes.
Image build evidence is retained in `reports/lab-image-symbolizer-build.log`.

After this image fix, `reports/lab-gpu-acceptance-20261023T020718Z.json` captured
the old s1 source successfully but had only **268** device-0 events, failing the
unchanged >1000 requirement. That failed acceptance is retained. The current
s1 calibration record `reports/s1-calibration-20261023T0210.json` is also retained;
formal T1.1 acceptance uses the later **2050-event** report cited above.

This acceptance does not certify T1.2 peak composition/fragmentation, model
diagnosis, patching, numerical equivalence, end-to-end repair, or T2.1 search.
