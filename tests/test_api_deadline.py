"""Admission deadlines with owned fake processes only; no GPU, network, or keys."""

import fcntl
import hashlib
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from uuid import uuid4

import pytest

from headroom.api.queue import AdmissionError, RunQueue, _preparation_group_alive
from headroom.orchestrator import FixRequest
from headroom.store.db import Store


def fake_prepare(script, *, delay=0, marker=None, descendant=None, deadline):
    assert "NEBIUS_API_KEY" not in __import__("os").environ
    assert "TAVILY_API_KEY" not in __import__("os").environ
    if marker:
        Path(marker).write_text(str(__import__("os").getpid()))
    if descendant:
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(30)",
            ]
        )
        Path(descendant).write_text(str(child.pid))
    if delay:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(delay)
    return FixRequest(script=str(script), target="fix-oom", max_seconds=1)


def fake_worker(request, *, store, run_root, run_id):
    folder = Path(run_root) / run_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "started").write_text(str(time.monotonic()))
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(30)


@pytest.fixture
def queue(tmp_path):
    script = tmp_path / "train.py"
    script.write_text("pass")
    store = Store(tmp_path / "store.db")
    queue = RunQueue(
        store,
        run_root=tmp_path / "jobs",
        admission_path=tmp_path / "admission.db",
        worker=fake_worker,
        deadline=4,
        grace=0.1,
    )
    queue.start()
    yield queue, script
    queue.close()
    assert not queue.thread.is_alive()
    assert not queue.expiry_thread.is_alive()
    store.close()


def submit(queue, script, **options):
    identifier = uuid4().hex
    queue.submit(
        identifier,
        {"kind": "fixture", "target": "fix-oom"},
        "owner",
        identifier,
        partial(fake_prepare, script, **options),
    )
    return identifier


def wait_until(predicate, timeout=8):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("Offline condition did not arrive")


def test_preparation_deadline_kills_owned_group_and_never_dispatches_worker(
    queue, tmp_path, monkeypatch
):
    monkeypatch.setenv("NEBIUS_API_KEY", "offline-sentinel-never-a-real-key")
    monkeypatch.setenv("TAVILY_API_KEY", "offline-sentinel-never-a-real-key")
    jobs, script = queue
    marker, descendant = tmp_path / "preparing", tmp_path / "descendant"
    with pytest.raises(AdmissionError) as failure:
        submit(jobs, script, delay=30, marker=marker, descendant=descendant)
    assert failure.value.status == 504
    assert marker.exists() and descendant.exists()
    assert not _preparation_group_alive(int(marker.read_text()))
    child_stat = Path(f"/proc/{descendant.read_text()}/stat")
    assert not child_stat.exists() or child_stat.read_text().rsplit(")", 1)[1].split()[0] == "Z"
    row = jobs.store.list_runs(1)[0]
    assert row["status"] == "timeout" and row["api_cleanup_verified"]
    assert row["reason"] == "preparation_deadline_exceeded"
    assert not (jobs.run_root / row["run_id"] / "started").exists()
    assert (jobs.run_root / row["run_id"] / "report.json").exists()
    assert not jobs.snapshot()["halted"] and jobs.snapshot()["preparing"] == 0


def test_worker_receives_only_time_left_after_preparation(queue):
    jobs, script = queue
    admitted = time.monotonic()
    run_id = submit(jobs, script, delay=1.5)
    wait_until(lambda: jobs.store.get_run(run_id).get("api_worker_finished"))
    row = jobs.store.get_run(run_id)
    started = float((jobs.run_root / run_id / "started").read_text())
    assert row["status"] == "timeout"
    assert started - admitted >= 1.5
    # A fresh four-second worker budget would finish after at least 5.5 seconds.
    assert time.monotonic() - admitted < 5.2
    assert row["api_deadline_at"] - row["api_admitted_at"] == 4
    assert row["api_cleanup_grace_seconds"] == 0.1


def test_waiting_job_expires_without_starting_and_slow_report_does_not_delay_watchdog(
    queue, monkeypatch
):
    from headroom.api import queue as module

    jobs, script = queue
    first = submit(jobs, script)
    wait_until(lambda: (jobs.run_root / first / "started").exists())

    def trusted_preparation(prepare, deadline):
        # This case isolates waiting expiry; the tests above exercise real
        # preparation spawn, cleanup and its share of the original deadline.
        assert time.monotonic() < deadline
        prepared = prepare(deadline=deadline)
        assert time.monotonic() < deadline
        return prepared, True

    monkeypatch.setattr(jobs, "_prepare", trusted_preparation)
    jobs.deadline = 1.2
    render = module.generate_report
    report_started = __import__("threading").Event()
    report_release = __import__("threading").Event()

    def slow_report(directory, *args, **kwargs):
        run_id = Path(directory).name
        if (
            run_id != first
            and jobs.store.get_run(run_id).get("reason") == "queue_deadline_exceeded"
        ):
            report_started.set()
            report_release.wait(8)
        return render(directory, *args, **kwargs)

    monkeypatch.setattr(module, "generate_report", slow_report)
    admitted = jobs.store.get_run(first)["api_admitted_at"]
    try:
        second = submit(jobs, script)
        row = jobs.store.get_run(second)
        assert row["api_execution_limit_seconds"] == 1.2
        assert row["api_deadline_at"] == row["api_admitted_at"] + 1.2
        assert any(event["kind"] == "run.queued" for event in jobs.store.events(second))
        assert report_started.wait(3)
        row = jobs.store.get_run(second)
        assert row["status"] == "timeout" and not row["api_worker_finished"]
        assert row["api_report_pending"] and not row["api_report_ready"]
        assert row["reason"] == "queue_deadline_exceeded"
        assert not (jobs.run_root / second / "started").exists()
        wait_until(lambda: jobs.store.get_run(first).get("api_worker_finished"))
        assert time.time() - admitted < 5.2
    finally:
        report_release.set()


def test_preparation_cleanup_uncertainty_freezes_new_admission(queue, monkeypatch):
    from headroom.api import queue as module

    jobs, script = queue
    stop = module._stop_preparation

    def uncertain(*args):
        assert stop(*args)  # Actually stop the fixture; only the verification is uncertain.
        return False

    monkeypatch.setattr(module, "_stop_preparation", uncertain)
    with pytest.raises(AdmissionError) as failure:
        submit(jobs, script)
    assert failure.value.status == 503 and jobs.snapshot()["halted"]
    row = jobs.store.list_runs(1)[0]
    assert row["status"] == "needs_human" and not row["api_cleanup_verified"]
    assert not (jobs.run_root / row["run_id"] / "started").exists()
    with pytest.raises(AdmissionError):
        submit(jobs, script)


def test_shutdown_terminates_preparation_before_return(queue, tmp_path):
    jobs, script = queue
    jobs.deadline = 30
    marker = tmp_path / "preparing"
    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(submit, jobs, script, delay=30, marker=marker)
        wait_until(marker.exists)
        jobs.close()
        with pytest.raises(AdmissionError) as failure:
            task.result(timeout=2)
    assert failure.value.status == 503
    assert not _preparation_group_alive(int(marker.read_text()))
    assert jobs.snapshot()["preparing"] == 0
    assert not list(jobs.run_root.glob("*/started"))


def test_expired_deadline_refuses_git_before_dispatch_and_uses_remaining_timeout(
    tmp_path, monkeypatch
):
    from headroom import repository

    calls = []
    monkeypatch.setattr(repository.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(
        repository.subprocess,
        "run",
        lambda args, **kwargs: calls.append(kwargs) or subprocess.CompletedProcess(args, 0, "", ""),
    )
    with pytest.raises(TimeoutError):
        repository._git(tmp_path, "status", deadline=99)
    assert calls == []
    repository._git(tmp_path, "status", deadline=103)
    assert calls[0]["timeout"] == 3


def test_reviewed_cache_lock_obeys_shared_deadline(tmp_path, monkeypatch):
    from headroom import repository

    extracted = tmp_path / "extracted"
    extracted.mkdir()
    payload = b"pass"
    (extracted / "train.py").write_bytes(payload)
    monkeypatch.setattr(
        repository, "NANOGPT_HASHES", {"train.py": hashlib.sha256(payload).hexdigest()}
    )
    monkeypatch.setattr(repository, "PROJECT_ROOT", tmp_path)
    cache = tmp_path / ".cache/reviewed/nanogpt"
    cache.mkdir(parents=True)
    with (cache / ".publish.lock").open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            repository._publish_reviewed_nanogpt(extracted, deadline=started + 0.1)
        assert time.monotonic() - started < 0.5
    assert not (cache / repository.NANOGPT_REF).exists()


def test_expired_archive_refuses_before_output_creation(tmp_path):
    from headroom.repository import _extract

    with pytest.raises(TimeoutError):
        _extract(tmp_path / "absent.tar", tmp_path / "output", deadline=time.monotonic() - 1)
    assert not (tmp_path / "output").exists()


def test_expired_spawn_entry_never_enters_worker_or_runtime(tmp_path):
    from headroom.api.queue import _process_entry

    called = []

    def forbidden(*args, **kwargs):
        called.append(True)
        raise AssertionError("Expired spawn must not enter worker")

    database = tmp_path / "expired.db"
    store = Store(database)
    run_id = uuid4().hex
    store.create_run(run_id)
    _process_entry(forbidden, {}, str(database), str(tmp_path), run_id, time.monotonic() - 1)
    assert called == []
    assert store.get_run(run_id)["status"] == "timeout"
    store.close()


def test_preparation_cleanup_does_not_signal_reused_pid(monkeypatch):
    from headroom.api import queue as module

    signals = []

    class EndedProcess:
        pid = 12345

        def join(self, timeout):
            pass

        def is_alive(self):
            return False

        def kill(self):
            signals.append("kill")

    monkeypatch.setattr(module, "_preparation_identity", lambda pid: ("new-start", pid, pid))
    monkeypatch.setattr(module, "_preparation_group_alive", lambda pid: True)
    monkeypatch.setattr(module.os, "killpg", lambda *args: signals.append(args))
    assert not module._stop_preparation(EndedProcess(), ("old-start", 12345, 12345), True)
    assert signals == []


def test_expired_api_source_preparation_does_not_touch_source_or_repository(tmp_path, monkeypatch):
    from headroom.api.app import ApiSettings, Submission, _prepare_submission

    def forbidden(*args, **kwargs):
        pytest.fail("Expired preparation cannot fetch or scan sources")

    monkeypatch.setattr("headroom.api.app.prepare_repository", forbidden)
    settings = ApiSettings(data_root=tmp_path)
    source = Submission(repo="https://github.com/example/repo", ref="a" * 40, cmd="python train.py")
    with pytest.raises(TimeoutError):
        _prepare_submission(settings, source, None, uuid4().hex, deadline=time.monotonic() - 1)
    assert not (tmp_path / "uploads").exists()


def orphan_supervisor(script, marker, descendant, idle, delay):
    from headroom.api.queue import _prepare_entry

    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe()
    child = context.Process(
        target=_prepare_entry,
        args=(
            partial(fake_prepare, script, delay=delay, marker=marker, descendant=descendant),
            time.monotonic() + 30,
            sender,
            os.getpid(),
        ),
        daemon=True,
    )
    child.start()
    sender.close()
    assert receiver.recv()[0] == "ready"
    receiver.send("proceed")
    if delay == 0:
        assert receiver.recv()[0] == "result"
        Path(idle).write_text("owned leader is waiting for supervisor cleanup")
    time.sleep(30)


@pytest.mark.parametrize("delay", [0, 30])
def test_supervisor_death_cleans_preparation_and_descendants(tmp_path, delay):
    from headroom.api.queue import _preparation_identity

    script = tmp_path / "train.py"
    script.write_text("pass")
    marker, descendant, idle = (tmp_path / name for name in ("preparing", "descendant", "idle"))
    supervisor = multiprocessing.get_context("spawn").Process(
        target=orphan_supervisor, args=(script, marker, descendant, idle, delay)
    )
    supervisor.start()
    preparation_pid = identity = None
    try:
        wait_until(lambda: marker.exists() and descendant.exists(), timeout=5)
        preparation_pid = int(marker.read_text())
        identity = _preparation_identity(preparation_pid)
        assert identity is not None
        if delay == 0:
            wait_until(idle.exists)
        supervisor.kill()
        supervisor.join(2)
        assert not supervisor.is_alive()
        wait_until(lambda: not _preparation_group_alive(preparation_pid), timeout=3)
    finally:
        if supervisor.is_alive():
            supervisor.kill()
        supervisor.join(2)
        if preparation_pid and identity:
            current = _preparation_identity(preparation_pid)
            if current is not None and current[0] == identity[0]:
                os.killpg(preparation_pid, signal.SIGKILL)


def test_admission_timestamps_are_sampled_after_sqlite_transaction_wait(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from headroom.api import queue as module

    clocks = {"wall": 1000.0, "monotonic": 100.0}
    store = Store(tmp_path / "time-map.db")
    jobs = RunQueue(
        store,
        run_root=tmp_path / "jobs",
        admission_path=tmp_path / "admission.db",
        worker=lambda *args, **kwargs: pytest.fail("This test never starts a worker"),
        mode="thread",
        deadline=4,
        clock=lambda: clocks["wall"],
    )
    original_connect = module.sqlite3.connect

    class DelayedAdmission:
        def __init__(self, *args, **kwargs):
            self.connection = original_connect(*args, **kwargs)

        def __enter__(self):
            return self.connection.__enter__()

        def __exit__(self, *args):
            result = self.connection.__exit__(*args)
            # Simulate DB lock/commit latency, including a wall-clock adjustment.
            clocks["monotonic"] += 30
            clocks["wall"] += 37
            return result

    monkeypatch.setattr(module, "sqlite3", SimpleNamespace(connect=DelayedAdmission))
    monkeypatch.setattr(module.time, "monotonic", lambda: clocks["monotonic"])
    supplied_deadlines = []

    def prepare(*, deadline):
        supplied_deadlines.append(deadline)
        return FixRequest(script=str(tmp_path / "train.py"))

    run_id = uuid4().hex
    try:
        jobs.submit(run_id, {"kind": "fixture"}, "owner", "fixture-ip", prepare)
        row = store.get_run(run_id)
        assert row["api_admitted_at"] == 1037
        assert row["api_deadline_at"] == 1041
        assert supplied_deadlines == [134]
        assert jobs.pending[0][2] == 134
        assert row["api_deadline_at"] - clocks["wall"] == 134 - clocks["monotonic"]
        with original_connect(jobs.admission_path) as connection:
            created = connection.execute(
                "SELECT created FROM admissions WHERE run_id=?", (run_id,)
            ).fetchone()[0]
        assert created == 1000  # IP quota retains the original attempt timestamp.
    finally:
        store.close()
