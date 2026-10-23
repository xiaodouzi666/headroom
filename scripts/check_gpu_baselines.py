#!/usr/bin/env python3
"""Collect full-size T0.6 GPU baselines; never treat CPU smoke as acceptance."""

import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import shlex
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAFE_ENV = {
    k: v for k, v in os.environ.items() if k not in {"NEBIUS_API_KEY", "TAVILY_API_KEY", "HF_TOKEN"}
}


def command(args, timeout=20):
    try:
        return subprocess.run(
            args, capture_output=True, text=True, check=False, timeout=timeout, env=SAFE_ENV
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "Control command timed out")
    except OSError as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))


def gpu_state():
    memory = command(
        [
            "nvidia-smi",
            "-i",
            "0",
            "--query-gpu=uuid,memory.total,memory.free",
            "--format=csv,noheader,nounits",
        ]
    )
    apps = command(
        [
            "nvidia-smi",
            "-i",
            "0",
            "--query-compute-apps=pid,process_name,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ]
    )
    state = {
        "at": datetime.datetime.now(datetime.UTC).isoformat(),
        "memory_raw": memory.stdout,
        "processes_raw": apps.stdout,
        "query_errors": memory.stderr + apps.stderr,
        "ready": False,
        "inspection_ok": False,
        "pids": [],
    }
    if memory.returncode or apps.returncode:
        state["reason"] = "GPU inspection failed"
        return state
    try:
        gpu_uuid, total_text, free_text = next(csv.reader(memory.stdout.splitlines()))
        total, free = int(total_text.strip()), int(free_text.strip())
        state.update(uuid=gpu_uuid.strip(), total_mib=total, free_mib=free)
        state["pids"] = [int(row[0].strip()) for row in csv.reader(apps.stdout.splitlines()) if row]
    except (ValueError, IndexError, StopIteration):
        state["reason"] = "Unrecognized nvidia-smi output"
        return state
    state["inspection_ok"] = True
    state["ready"] = not state["pids"] and total >= 23 * 1024 and free >= total * 0.95
    state["reason"] = "ready" if state["ready"] else "Full-size baseline capacity unavailable"
    return state


def inspect_container(name):
    p = command(["docker", "inspect", "--format", "{{json .State}}", name])
    if p.returncode:
        return None
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return None


def docker_command(case, name, image):
    args = [
        "docker",
        "run",
        "--name",
        name,
        "--gpus",
        "device=0",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "256",
        "--memory",
        "32g",
        "--cpus",
        "8",
        "--user",
        "65534:65534",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m",
        "--tmpfs",
        "/work:rw,nosuid,nodev,size=64m",
        "--mount",
        f"type=bind,src={ROOT / '.venv'},dst=/opt/venv,readonly",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "PYTHONUNBUFFERED=1",
        "--env",
        "OMP_NUM_THREADS=8",
    ]
    if case["id"] == "nanogpt":
        args += [
            "--mount",
            f"type=bind,src={ROOT / case['source_cache']},dst=/repo,readonly",
            "--mount",
            f"type=bind,src={ROOT / case['dataset_cache']},dst=/input,readonly",
            "--workdir",
            "/repo",
        ]
        target = shlex.split(case["command"])
        if target.pop(0) != "python":
            raise ValueError("nanoGPT command must invoke python directly")
    else:
        args += [
            "--mount",
            f"type=bind,src={ROOT / 'scenarios'},dst=/cases,readonly",
            "--workdir",
            "/work",
        ]
        target = [f"/cases/{case['id']}/train.py", "--steps", "20", "--device", "cuda"]
    return args + ["--entrypoint", "/opt/venv/bin/python", image] + target


def read_events(stdout):
    events = []
    for line in stdout.splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                events.append(value)
        except json.JSONDecodeError:
            continue
    return events


def run_case(case, directory, image):
    before = gpu_state()
    if not before["ready"]:
        return {"id": case["id"], "status": "blocked", "before": before}
    folder = directory / case["id"]
    folder.mkdir()
    name = "headroom-baseline-" + uuid.uuid4().hex[:12]
    args = docker_command(case, name, image)
    limit = 180 if case["id"] == "nanogpt" else (60 if case["expected_mode"] == "oom" else 300)
    record = {
        "id": case["id"],
        "command": args,
        "timeout_seconds": limit,
        "before": before,
        "gpu_observations": [],
        "full_size": True,
        "scope": "T0.6 baseline evidence only",
    }
    if case["id"] != "nanogpt":
        record["source_sha256"] = hashlib.sha256((ROOT / case["script"]).read_bytes()).hexdigest()
    started = time.monotonic()
    reason = None
    state = None
    own_pids = set()
    workload_seconds = None
    cleanup_actions = []
    with (folder / "stdout.txt").open("w") as out, (folder / "stderr.txt").open("w") as err:
        proc = subprocess.Popen(args, stdout=out, stderr=err, text=True, env=SAFE_ENV)
        try:
            while proc.poll() is None:
                if time.monotonic() - started >= limit:
                    reason = "timeout"
                    break
                state = inspect_container(name)
                observed = gpu_state()
                record["gpu_observations"].append(observed)
                own_pid = state.get("Pid") if state else None
                if own_pid:
                    own_pids.add(own_pid)
                foreign = [pid for pid in observed["pids"] if pid not in own_pids]
                if not observed["inspection_ok"] or foreign:
                    reason = (
                        "gpu_inspection_failed" if not observed["inspection_ok"] else "shared_gpu"
                    )
                    break
                time.sleep(1)
        finally:
            workload_seconds = time.monotonic() - started
            if proc.poll() is None:
                for action in (["docker", "stop", "--time", "2", name], ["docker", "kill", name]):
                    result = command(action)
                    cleanup_actions.append(
                        {"command": action, "exit_code": result.returncode, "stderr": result.stderr}
                    )
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        proc.kill()
                        proc.wait(timeout=10)
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        cleanup_actions.append(
                            {
                                "command": ["terminate Docker client"],
                                "exit_code": 1,
                                "stderr": str(exc),
                            }
                        )
            state = inspect_container(name) or state
            cleanup = command(["docker", "rm", "-f", name])
            cleanup_actions.append(
                {"command": cleanup.args, "exit_code": cleanup.returncode, "stderr": cleanup.stderr}
            )
    elapsed = time.monotonic() - started
    after = gpu_state()
    remaining = command(
        ["docker", "ps", "--all", "--filter", f"name={name}", "--format", "{{.Names}}"]
    )
    cleanup_verified = (
        cleanup.returncode == 0
        and remaining.returncode == 0
        and not remaining.stdout.strip()
        and after["inspection_ok"]
        and not own_pids.intersection(after["pids"])
    )
    if not cleanup_verified:
        reason = "cleanup_failed"
    elif after["pids"]:
        reason = reason or "shared_gpu"
    stdout = (folder / "stdout.txt").read_text()
    stderr = (folder / "stderr.txt").read_text()
    events = read_events(stdout)
    steps = [e for e in events if e.get("event") == "step"]
    terminal = events[-1] if events else {}
    peaks = [
        e.get("peak_allocated_bytes")
        for e in events
        if isinstance(e.get("peak_allocated_bytes"), (float, int))
    ]
    reserved_peaks = [
        e["peak_reserved_bytes"]
        for e in events
        if isinstance(e.get("peak_reserved_bytes"), (float, int))
    ]
    cuda_oom = bool(
        re.search(
            r"(?m)^torch(?:\.cuda)?\.OutOfMemoryError:\s+CUDA out of memory\b",
            stderr,
            re.IGNORECASE,
        )
    )
    if reason:
        outcome = reason
    elif state and state.get("OOMKilled"):
        outcome = "container_host_memory_oom"
    elif proc.returncode != 0 and cuda_oom:
        outcome = (
            "cuda_oom"
            if case["id"] == "nanogpt" or workload_seconds <= 60
            else "cuda_oom_after_60s"
        )
    elif (
        proc.returncode == 0
        and case["id"] != "nanogpt"
        and [event.get("step") for event in steps] == list(range(1, 21))
        and terminal.get("steps") == 20
        and peaks
        and reserved_peaks
        and (terminal.get("event") == "completed" or terminal.get("status") == "completed")
    ):
        outcome = "completed_20_steps"
    else:
        outcome = "error_or_incomplete_evidence"
    expected = case.get("expected_mode", "oom")
    observed_ok = (
        outcome == "cuda_oom"
        if expected == "oom"
        else (
            outcome == "completed_20_steps"
            or expected == "oom_or_reclaim"
            and outcome == "cuda_oom"
        )
    )
    record.update(
        status=outcome,
        observed_check_passed=observed_ok,
        exit_code=proc.returncode,
        container_state=state,
        cleanup_exit=cleanup.returncode,
        cleanup_actions=cleanup_actions,
        cleanup_verified=cleanup_verified,
        workload_seconds=workload_seconds,
        wall_seconds_including_cleanup=elapsed,
        step_events=len(steps),
        peak_allocated_bytes=max(peaks) if peaks else None,
        peak_reserved_bytes=max(reserved_peaks) if reserved_peaks else None,
        stdout_path=str(folder / "stdout.txt"),
        stderr_path=str(folder / "stderr.txt"),
        after=after,
        readme_measurement_recorded=False,
        t0_6_accepted=False,
    )
    if case["id"] == "nanogpt" and observed_ok:
        trace = ROOT / "repos/nanogpt.oom.txt"
        if trace.exists() and trace.read_text() != stderr:
            record["trace_note"] = (
                "Existing traceback retained; current traceback is in run directory"
            )
        elif not trace.exists():
            trace.write_text(stderr)
    (folder / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only", action="store_true", help="Inspect prerequisites; launch no workload"
    )
    parser.add_argument(
        "--case", action="append", default=[], help="Scenario ID; default all eight plus nanoGPT"
    )
    args = parser.parse_args()
    cases = json.loads((ROOT / "scenarios/INDEX.yaml").read_text())["scenarios"]
    cases += [json.loads((ROOT / "repos/nanogpt.yaml").read_text())]
    available = {case["id"] for case in cases}
    if set(args.case) - available:
        parser.error("Unknown scenario ID")
    if args.case:
        cases = [case for case in cases if case["id"] in args.case]
    initial = gpu_state()
    for case in cases:
        if case["id"] == "nanogpt":
            repo = ROOT / case["source_cache"]
            head = command(["git", "-C", str(repo), "rev-parse", "HEAD"])
            dirty = command(["git", "-C", str(repo), "status", "--porcelain"])
            if (
                head.returncode
                or head.stdout.strip() != case["ref"]
                or dirty.returncode
                or dirty.stdout
            ):
                initial.update(ready=False, reason="nanoGPT pin or clean source check failed")
            if not all(
                (ROOT / case["dataset_cache"] / f"{split}.bin").is_file()
                for split in ("train", "val")
            ):
                initial.update(ready=False, reason="nanoGPT input data missing")
    image = command(
        ["docker", "image", "inspect", "--format", "{{.Id}}", "headroom-lab:py312-cu124"]
    )
    if image.returncode:
        initial.update(ready=False, reason="Lab Docker image unavailable")
    run_id = (
        datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    )
    report = {
        "run_id": run_id,
        "preflight": initial,
        "image": image.stdout.strip(),
        "check_only": args.check_only,
        "workloads_launched": 0,
        "cases": [],
        "t0_6_accepted": False,
    }
    if initial["ready"] and not args.check_only:
        directory = ROOT / "runs" / "phase0-baselines" / run_id
        directory.mkdir(parents=True)
        for case in cases:
            result = run_case(case, directory, image.stdout.strip())
            report["cases"].append(result)
            report["workloads_launched"] += int(result["status"] != "blocked")
            print(case["id"], result["status"], flush=True)
            if result["status"] in {
                "blocked",
                "shared_gpu",
                "gpu_inspection_failed",
                "cleanup_failed",
            }:
                break
    path = ROOT / "reports" / f"gpu-baseline-{run_id}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "report": str(path),
                "ready": initial["ready"],
                "reason": initial["reason"],
                "workloads_launched": report["workloads_launched"],
            }
        )
    )
    if not initial["ready"]:
        return 78
    if args.check_only:
        return 0
    return (
        0
        if len(report["cases"]) == len(cases)
        and all(case.get("observed_check_passed") for case in report["cases"])
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
