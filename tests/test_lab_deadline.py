"""CPU-only shared deadline tests; no inference or GPU acceptance claims."""

import json
import socket
import time
from pathlib import Path

import pytest

from headroom.lab import deadline, docker
from headroom.lab.runner import run_argv, run_script


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in deadline tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.mark.parametrize("seconds,reserve", [(1, 0.1), (30, 3), (120, 5)])
def test_host_and_capture_limits_share_one_absolute_clock(tmp_path, monkeypatch, seconds, reserve):
    monkeypatch.setattr(deadline.time, "monotonic_ns", lambda: 10_000_000_000)
    record = deadline.publish_deadline(tmp_path, seconds)
    assert record["hard_deadline_monotonic_ns"] == int((10 + seconds) * 1e9)
    assert record["capture_deadline_monotonic_ns"] == int((10 + seconds - reserve) * 1e9)
    monkeypatch.setattr(deadline.time, "monotonic_ns", lambda: 10_050_000_000)
    remaining, observation = deadline.capture_window(tmp_path, seconds)
    assert remaining == pytest.approx(seconds - reserve - 0.05)
    assert observation["clock_verified"] is True


@pytest.mark.parametrize("damage", ["clock", "duration", "link", "large", "past"])
def test_control_mismatch_and_untrusted_files_never_extend_capture(tmp_path, damage):
    record = deadline.publish_deadline(tmp_path, 30)
    path = tmp_path / "deadline.json"
    path.chmod(0o600)
    if damage == "clock":
        record["clock_identity"]["monotonic_offset"]["seconds"] += 1
    elif damage == "duration":
        record["hard_deadline_monotonic_ns"] += 1000
    elif damage == "link":
        target = tmp_path / "other.json"
        path.rename(target)
        path.symlink_to(target)
    elif damage == "large":
        path.write_text(" " * (deadline.MAX_CONTROL_BYTES + 1))
    else:
        record["started_monotonic_ns"] += 10**18
        record["hard_deadline_monotonic_ns"] += 10**18
        record["capture_deadline_monotonic_ns"] += 10**18
    if damage not in {"link", "large"}:
        path.write_text(json.dumps(record))
    with pytest.raises(deadline.DeadlineUnavailable):
        deadline.capture_window(tmp_path, 30)


def test_expired_window_is_zero_not_a_new_relative_duration(tmp_path, monkeypatch):
    monkeypatch.setattr(deadline.time, "monotonic_ns", lambda: 1_000_000_000)
    deadline.publish_deadline(tmp_path, 1)
    monkeypatch.setattr(deadline.time, "monotonic_ns", lambda: 3_000_000_000)
    remaining, observation = deadline.capture_window(tmp_path, 1)
    assert remaining == 0 and observation["expired_before_target"]


def test_control_mount_cannot_be_redirected_to_writable_output(monkeypatch):
    monkeypatch.setenv("HEADROOM_CONTROL_DIR", "/out")
    with pytest.raises(deadline.DeadlineUnavailable, match="fixed Lab mount"):
        deadline.configured_control()


@pytest.mark.parametrize("name", ["control\ninvalid", "control,invalid"])
def test_control_mount_rejects_ambiguous_paths(tmp_path, monkeypatch, name):
    monkeypatch.setattr(docker, "docker_binary", lambda: "/usr/bin/docker")
    monkeypatch.setattr(
        docker, "require_runtime_image", lambda *args, **kwargs: {"image_id": "sha256:" + "a" * 64}
    )
    for directory in ("headroom", "source", "artifacts", name):
        (tmp_path / directory).mkdir()
    with pytest.raises(ValueError, match="Deadline control mount path is invalid"):
        docker.create_arguments(
            name="headroom-lab-" + "a" * 32,
            project_root=tmp_path,
            source=tmp_path / "source",
            output=tmp_path / "artifacts",
            environment={},
            command=["/opt/venv/bin/python", "train.py"],
            device="cpu",
            control=tmp_path / name,
        )


def test_real_cpu_soft_timeout_retains_complete_capture_and_readonly_clock(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "infer.py"
    script.write_text(
        "import json, time\nfrom pathlib import Path\n"
        "try:\n    Path('/control/deadline.json').write_text('{}')\n"
        "except OSError:\n    print('CONTROL_READONLY_VERIFIED')\n"
        "else:\n    raise AssertionError('control must be read-only')\n"
        "while True:\n    time.sleep(0.02)\n"
    )
    result = run_script(script, device="cpu", max_seconds=6, run_root=tmp_path / "runs")
    assert result["status"] == "timeout" and result["capture_complete"], result
    assert result["steps"] == 0 and result["loss_series"] == []
    assert result["cleanup_verified"] and not result["execution"]["timed_out"]
    observed = result["deadline_observation"]
    assert observed["clock_verified"] and observed["remaining_capture_seconds"] < 5.4
    assert (
        observed["capture_deadline_monotonic_ns"]
        == result["execution"]["deadline_control"]["capture_deadline_monotonic_ns"]
    )
    artifacts = Path(result["artifact_dir"])
    manifest = json.loads((artifacts.parent / "manifest.json").read_text())
    assert manifest["image_id"] == result["image_id"] == result["execution"]["image_id"]
    assert manifest["image_id"].startswith("sha256:")
    assert "CONTROL_READONLY_VERIFIED" in (artifacts.parent / "stdout.log").read_text()
    for name in ("result.json", "snapshot.json", "snapshot.pickle", "memory_stats.json"):
        assert (artifacts / name).is_file()


@pytest.mark.parametrize("behavior", ["ignored", "blocked"])
def test_real_cpu_uncapturable_target_hits_unchanged_hard_deadline(tmp_path, behavior):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "forever.py"
    setup = (
        "signal.signal(signal.SIGALRM, signal.SIG_IGN)"
        if behavior == "ignored"
        else "signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})"
    )
    blocked_work = (
        "read_fd, write_fd = os.pipe()\nos.read(read_fd, 1)\n"
        if behavior == "blocked"
        else "while True:\n    time.sleep(0.02)\n"
    )
    script.write_text(
        "import os, signal, time\nfrom pathlib import Path\n"
        + setup
        + "\nprint('MAIN_STARTED_VERIFIED', flush=True)\n"
        + blocked_work
    )
    started = time.monotonic()
    result = run_script(script, device="cpu", max_seconds=5, run_root=tmp_path / "runs")
    elapsed = time.monotonic() - started
    assert result["status"] == "timeout" and result["execution"]["timed_out"], result
    assert result["cleanup_verified"]
    assert "MAIN_STARTED_VERIFIED" in (Path(result["run_dir"]) / "stdout.log").read_text()
    control = result["execution"]["deadline_control"]
    assert control["hard_deadline_monotonic_ns"] - control["started_monotonic_ns"] == 5_000_000_000
    assert 5 <= elapsed < 20  # existing bounded Docker teardown may follow the hard cutoff


def test_real_cpu_parent_and_late_child_share_deadline(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "parent.py").write_text(
        "import subprocess, sys, time\n"
        "time.sleep(1)\n"
        "subprocess.run([sys.executable, 'child.py'])\n"
    )
    (source / "child.py").write_text("import time\nwhile True:\n    time.sleep(0.02)\n")
    result = run_argv(
        source, ["python", "parent.py"], device="cpu", max_seconds=8, run_root=tmp_path / "runs"
    )
    run = Path(result["run_dir"])
    ready = [
        json.loads(path.read_text()) for path in (run / "artifacts").rglob("capture-ready.json")
    ]
    assert len(ready) == 2, result
    observations = [item["deadline_observation"] for item in ready]
    assert all(item["clock_verified"] for item in observations)
    assert len({item["hard_deadline_monotonic_ns"] for item in observations}) == 1
    assert len({item["capture_deadline_monotonic_ns"] for item in observations}) == 1
    assert (
        max(item["remaining_capture_seconds"] for item in observations)
        - min(item["remaining_capture_seconds"] for item in observations)
        > 0.5
    )
    assert result["status"] == "timeout" and result["cleanup_verified"], result


def test_real_cpu_clock_mismatch_stops_before_user_main(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "main.py"
    script.write_text("from pathlib import Path\nPath('/out/unsafe-main').write_text('ran')\n")
    original = deadline.clock_identity

    def wrong_host_clock():
        identity = original()
        identity["monotonic_offset"]["seconds"] += 1
        return identity

    monkeypatch.setattr(deadline, "clock_identity", wrong_host_clock)
    result = run_script(script, device="cpu", max_seconds=15, run_root=tmp_path / "runs")
    assert result["status"] == "error" and result["cleanup_verified"], result
    assert not (Path(result["artifact_dir"]) / "unsafe-main").exists()
    assert result["capture_complete"] is False
    assert "clock mismatch" in (Path(result["artifact_dir"]) / "traceback.txt").read_text()


def test_real_cpu_natural_no_optimizer_exit_remains_completed_zero_steps(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "natural.py"
    script.write_text(
        "import torch\nm = torch.nn.Linear(2, 1)\n"
        "with torch.no_grad():\n    result = m(torch.ones(1, 2))\n"
    )
    result = run_script(script, device="cpu", max_seconds=15, run_root=tmp_path / "runs")
    assert result["status"] == "completed" and result["termination_reason"] == "script_exit", result
    assert result["steps"] == 0 and result["loss_series"] == []
    assert result["deadline_observation"]["clock_verified"] and result["cleanup_verified"]


def test_distinct_time_namespace_requires_known_equal_monotonic_offset():
    host = deadline.clock_identity()
    other = host | {"time_namespace_inode": host["time_namespace_inode"] + 1}
    assert deadline.same_monotonic_clock(host, other)
    assert not deadline.same_monotonic_clock(host, other | {"monotonic_offset": None})
    assert not deadline.same_monotonic_clock(host, other | {"boot_id": "different"})
    assert not deadline.same_monotonic_clock(
        host, other | {"monotonic_offset": {"seconds": 1, "nanoseconds": 0}}
    )


@pytest.mark.parametrize("updates", [0, 20])
def test_real_cpu_swallowed_soft_timeout_cannot_become_completed(tmp_path, updates):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "swallow.py"
    script.write_text(
        "import time, torch\n"
        "m=torch.nn.Linear(1,1)\no=torch.optim.SGD(m.parameters(),lr=.01)\n"
        "x=torch.ones(1,1)\n"
        "try:\n    while True: time.sleep(.02)\n"
        "except BaseException:\n    pass\n"
        f"for _ in range({updates}):\n"
        "    o.zero_grad()\n    m(x).square().mean().backward()\n    o.step()\n"
    )
    result = run_script(script, device="cpu", max_seconds=10, run_root=tmp_path / "runs")
    assert result["status"] == "timeout" and result["deadline_reached"] is True, result
    assert result["steps"] == updates
    assert result["deadline_observation"]["triggered"] is True
    assert result["capture_complete"] and not result["execution"]["timed_out"]
    assert result["cleanup_verified"]


def test_real_cpu_completed_helper_then_soft_timeout_is_timeout(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "long.py").write_text("import time\nwhile True:\n    time.sleep(.02)\n")
    result = run_argv(
        source,
        ["/bin/sh", "-c", "python -c 'print(123)'; python long.py"],
        device="cpu",
        max_seconds=8,
        run_root=tmp_path / "runs",
    )
    assert result["status"] == "timeout" and not result["execution"]["timed_out"], result
    assert result["execution_capture"]["complete"]
    assert result["execution_capture"]["captured_process_count"] == 2
    assert result["execution_capture"]["observed_timeout_captures"]
    assert result["execution_capture"]["selection"]["status"] == "unavailable"
    assert result["cleanup_verified"]


@pytest.mark.parametrize(
    "root_exit,other_error,killed",
    [(0, False, False), (7, False, False), (1, True, False), (1, False, True)],
)
def test_descendant_timeout_cannot_mask_other_root_or_capture_failures(
    tmp_path, monkeypatch, root_exit, other_error, killed
):
    from test_multicapture import capture, write_capture

    from headroom.lab import runner

    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("pass\n")

    def execute(*, run_dir, **kwargs):
        write_capture(run_dir, "artifacts", capture(1, primary=True))
        timed_out = capture(7, target=True, status="timeout")
        timed_out["termination_reason"] = "timeout"
        timed_out["deadline_reached"] = True
        write_capture(run_dir, "artifacts/processes/7", timed_out)
        if other_error:
            write_capture(run_dir, "artifacts/processes/8", capture(8, status="error"))
        return {
            "state": {"ExitCode": root_exit, "OOMKilled": killed, "Running": False},
            "timed_out": False,
            "cleanup_verified": True,
            "image_id": "synthetic",
        }

    monkeypatch.setattr(runner.docker, "execute", execute)
    result = run_argv(source, ["/bin/sh", "launch.sh"], device="cpu", run_root=tmp_path / "runs")
    assert result["status"] == "error"
    assert result["execution"]["state"]["ExitCode"] == root_exit
    assert result["execution_capture"]["observed_timeout_captures"]


def test_expired_before_target_marks_persistent_deadline(tmp_path, monkeypatch):
    from headroom.lab import hooks

    monkeypatch.setattr(hooks, "configured_control", lambda: tmp_path)
    monkeypatch.setattr(
        hooks,
        "capture_window",
        lambda *_: (0.0, {"basis": "offline_fixture", "expired_before_target": True}),
    )
    session = hooks.CaptureSession(tmp_path / "capture", device="cpu")
    with pytest.raises(hooks.CaptureTimeout) as expired:
        session.start()
    result = session.finish(exc=expired.value)
    assert result["status"] == "timeout"
    assert result["deadline_reached"] and result["deadline_observation"]["triggered"]
    assert result["steps"] == 0 and result["capture_complete"]
