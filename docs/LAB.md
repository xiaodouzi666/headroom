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


## Observation deadline within the existing hard limit

Production Lab launches now publish control/deadline.json after container
creation and immediately before start. That directory is mounted read-only at
/control. The host and every captured Python child use this one absolute
CLOCK_MONOTONIC deadline; a later child does not receive a new full max_seconds.

The host hard deadline remains start + max_seconds. The internal observation
deadline is earlier by min(5 seconds, 10% of max_seconds), reserving time inside
the original limit for snapshot capture and serialization. For max_seconds=30,
the observation window ends at 27 seconds and the hard cutoff remains 30 seconds.
This is a maximum window, not a minimum runtime: the Lab does not sleep merely
to consume the reserve. Existing global job deadlines are unchanged, and the
existing bounded container teardown still runs after exit or a hard cutoff.

The control record and capture result retain both deadlines, the reserve, the
remaining window seen by that Python process, and clock identity observations.
On this host Docker uses a distinct time namespace inode with the same
monotonic offset. Compatibility therefore requires a matching boot ID and an
explicitly readable, equal CLOCK_MONOTONIC offset from /proc/self/timens_offsets.
An inode is recorded for diagnostics, not treated as proof of a different clock.
Missing/mismatched offsets or malformed/missing control records fail setup
before the target main. A target-writable /out file is never accepted as the
deadline authority, and the control mount path cannot be redirected there.

The internal SIGALRM marks deadline_reached and raises CaptureTimeout while
enough time remains to attempt the existing capture finalization. If the target
catches BaseException and returns or performs more optimizer updates afterward,
that persistent deadline flag still makes the final result timeout. It remains
status=timeout, including for a script without an optimizer. An ignored alarm, blocked native operation, slow
setup, oversized capture or other failure to finish is still cut off by the
original host limit; complete evidence is not guaranteed when work cannot
respond or serialize within the reserve. The result distinguishes a complete
internal timeout from execution.timed_out=true hard termination. Neither is
converted to completed. A completed helper followed by a complete child timeout
is reported as timeout only when the whole roster contains completed/timeout
records and the root exit/state agrees. A separate child error, missing capture,
root exit 0/7 or container OOM kill cannot be hidden by that aggregation. Each
capture-ready.json also saves its observed deadline.
If a parent exits first, Docker can end a child before the child serializes its
final record; the existing incomplete capture roster remains explicit, even
though both ready records prove they used the same cutoff.

Capture finalization first writes an atomic partial result. It records the real
execution status, already observed optimizer steps/losses, deadline state, and
available peaks; unknown values remain null. Peaks copied before the final CUDA
query are explicitly labeled as last-completed-update observations. The allocator
snapshot remains the first CUDA operation during exception finalization. Once
the end-of-capture peaks are measured, a new checkpoint preserves them before
serialization.

Every checkpoint has capture_complete=false, finalization_incomplete=true and a
finalization_stage. A timeout stays timeout; provisional completed/OOM execution
is labeled error/capture_incomplete, with its original execution_status retained.
Small memory/traceback/environment artifacts are written before the unchanged
full snapshot history. Snapshot pickle and JSON use temporary files followed by
atomic replacement. artifact_writes distinguishes pending, complete and failed
files; an interrupted temporary file is not a complete artifact. Only final
serialization and the original capture checks can produce the final result.

If the hard cutoff interrupts a large history conversion, the host preserves
that partial result and original artifact directory. It cannot be used as a
complete repair capture or a passing target, and missing snapshot JSON does not
become a synthetic timeline. This changes neither the 200,000-entry history
setting nor the observation reserve or hard deadline. It cannot guarantee full
serialization of arbitrary history within a fixed reserve.

A naturally returning no-optimizer script remains completed with steps=0 and an
empty loss sequence. This does not manufacture training updates, step timing,
loss equivalence or a passing repair target. Those existing verification limits
are unchanged; see VERIFY.md.

Offline reproduction:

    source scripts/env.sh
    .venv/bin/python reports/lab-deadline-20261024/offline_tests.py -q tests/test_lab_deadline.py tests/test_lab_hooks.py tests/test_lab_docker.py tests/test_runner.py tests/test_lab_finalize.py

Tests use CPU-only Docker with no network and an independent host DNS/socket and
real-project-.env read guard. Clock probes and preserved failed test logs live
under reports/lab-deadline-20261024/. No model or GPU acceptance is implied.

The self-contained runtime is described in [LAB_RUNTIME.md](LAB_RUNTIME.md).
Lab create uses the immutable image ID returned by its contract/lock preflight,
without mounting the host virtual environment. The execution result and run
manifest both preserve the actual container image ID.


## Logical updates and checkpoint precision — 2026-10-25

The capture limit counts complete logical optimizer updates. Ordinary outer
optimizer steps retain their behavior. For the reviewed optimizer-in-backward
shape, multiple per-parameter callbacks count as one update only after the outer
`Tensor.backward` returns successfully and all observed gradient parameters have
been updated. Callback counts and coverage evidence are retained separately.
Exceptions, incomplete coverage or unrecognized shapes cannot manufacture 20
complete updates. Closure/empty-gradient cases do not gain a false complete
parameter-coverage claim.

The precision observer explicitly supports the pinned PyTorch 2.5.1
non-reentrant checkpoint implementation with its default context. It requires
initial-forward observation and enters an actual thread-local operation mode
before the CUDA worker recomputation function body, including functional-only
operations. Entry/exit, early-stop and error counters are recorded. Unknown API
shapes, reentrant/custom contexts, unseen initial forwards and unregistered
threads remain unknown. The mode is restored on success and exceptions; it is
not a blanket assertion that every native operator dtype has been proved.
Two real CUDA observer regressions distinguish FP32 from internal BF16 even when
the returned tensor is FP32. See [the observer report](../reports/checkpoint-precision-observer-20261025.md).

Snapshot JSON now uses a versioned lossless shared frame/stack encoding. The
formal `headroom.lab.snapshot_codec.read_snapshot_artifact` reader accepts both
old native snapshots and the new encoding within the unchanged 512 MiB file
limit, with bounded decoded structures. The original pickle remains untouched;
host readers do not unpickle it. Existing captured events and stacks are retained;
the original 200,000-event history capacity and deadlines have not increased.
These capture and manual-reference validations do not count as model-generated
repairs, and all older failed evidence remains preserved.
