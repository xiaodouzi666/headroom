"""One scheduler thread; production jobs run in supervised spawn processes."""

import hashlib
import json
import multiprocessing
import re
import sqlite3
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from headroom.api.security import RUN_ID, job_directory, open_regular
from headroom.lab import docker
from headroom.lab.envs import HOST_ENV
from headroom.orchestrator import FixRequest, run_fix
from headroom.report import generate_report
from headroom.store.db import Store

TERMINAL = {"completed", "failed", "needs_human", "budget_exceeded", "cancelled", "timeout"}


class AdmissionError(RuntimeError):
    def __init__(self, reason, status=429):
        super().__init__(reason)
        self.status = status


def _finish_result(store, run_id, result):
    state = store.get_run(run_id)
    result = result if isinstance(result, dict) else {}
    status = result.get("status", state.get("status"))
    if status not in TERMINAL:
        status = "needs_human"
    store.update_run(run_id, status=status, target_met=result.get("target_met", False))
    if not store.events(run_id):
        store.add_event(run_id, "run.done" if status == "completed" else "needs_human", {})


def _process_entry(worker, request, store_path, run_root, run_id):
    store = Store(store_path)
    try:
        result = (worker or run_fix)(
            FixRequest.model_validate(request), store=store, run_root=Path(run_root), run_id=run_id
        )
        _finish_result(store, run_id, result)
    except Exception:  # noqa: BLE001 - preserve failed worker state and halt unsafe scheduling
        store.update_run(
            run_id,
            status="failed",
            reason="Worker failed; inspect local evidence",
            target_met=False,
        )
        store.add_event(run_id, "run.failed", {"reason": "worker_error"})
    finally:
        store.close()


def cleanup_owned_lab(run_root, run_id):
    """Only manifests beneath this job can identify containers eligible for cleanup."""
    try:
        directory = job_directory(run_root, run_id)
        lab = directory / "lab"
        if not lab.exists():
            return True
        if lab.is_symlink() or not lab.is_dir():
            return False
        for item in lab.iterdir():
            if not RUN_ID.fullmatch(item.name) or item.is_symlink() or not item.is_dir():
                return False
            if not (item / "manifest.json").exists():
                # Lab writes manifest before docker create; source-copy-only directories
                # cannot have launched a container through the supported Lab runner.
                continue
            with open_regular(item, "manifest.json", 2 * 1024 * 1024) as handle:
                manifest = json.load(handle)
            if manifest.get("image") != docker.IMAGE or not isinstance(
                manifest.get("command"), list
            ):
                return False
            name = "headroom-lab-" + item.name
            inspected = subprocess.run(
                [docker.docker_binary(), "inspect", "--type", "container", name],
                env=HOST_ENV,
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            if inspected.returncode:
                message = inspected.stderr.lower()
                if "no such object" in message or "no such container" in message:
                    continue
                return False
            details = json.loads(inspected.stdout)[0]
            mounts = {m.get("Destination"): m.get("Source") for m in details.get("Mounts", [])}
            if (
                details.get("Name") != "/" + name
                or mounts.get("/source") != str(item / "source")
                or mounts.get("/out") != str(item / "artifacts")
            ):
                return False
            container_id = details.get("Id", "")
            if not re.fullmatch(r"[0-9a-f]{64}", container_id):
                return False
            # Remove the inspected immutable ID, never a replacement that races
            # to reuse the manifest-derived name after the ownership check.
            if not docker.cleanup_container(container_id).get("cleanup_verified"):
                return False
        return True
    except (OSError, ValueError, KeyError, IndexError, RuntimeError, subprocess.SubprocessError):
        return False


class RunQueue:
    def __init__(
        self,
        store,
        *,
        run_root,
        admission_path,
        worker=None,
        mode="process",
        deadline=600,
        grace=5,
        clock=time.time,
    ):
        self.store, self.run_root = store, Path(run_root)
        self.worker, self.mode = worker, mode
        self.deadline, self.grace, self.clock = deadline, grace, clock
        self.pending = deque()
        self.preparing = set()
        self.running = None
        self.halted = False
        self.closing = False
        self.condition = threading.Condition()
        self.admission_path = Path(admission_path)
        self.admission_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.admission_path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS admissions (run_id TEXT PRIMARY KEY, ip TEXT, created REAL)"
            )
        self.thread = threading.Thread(target=self._loop, name="headroom-api-queue", daemon=True)

    def start(self):
        # Never silently resume a previously active paid/GPU job after a server restart.
        for row in self.store.list_runs(10000):
            if not row.get("api_owner") or row.get("api_worker_finished") is True:
                continue
            if row["status"] != "queued":
                # A worker can commit a terminal status before supervisor cleanup.
                # Such rows still require recovery; terminal does not mean safe to reuse GPU.
                self.halted = True
                self.store.update_run(
                    row["run_id"],
                    status="needs_human",
                    target_met=False,
                    reason="Prior worker cleanup requires operator verification",
                )
                self.store.add_event(row["run_id"], "needs_human", {"reason": "recovery_required"})
            else:
                self.store.update_run(
                    row["run_id"],
                    status="needs_human",
                    api_worker_finished=True,
                    api_cleanup_verified=True,
                    reason="Server restarted before this queued run started",
                )
                self.store.add_event(row["run_id"], "needs_human", {"reason": "server_restart"})
        self.thread.start()

    def snapshot(self):
        with self.condition:
            return {
                "running": self.running,
                "pending": len(self.pending),
                "preparing": len(self.preparing),
                "capacity": 3,
                "halted": self.halted,
                "closing": self.closing,
            }

    def submit(self, run_id, request, owner, client_ip, prepare):
        # Preparation may fetch a repository. Reserve admission/one capacity slot
        # under short locks, then release both locks before any slow I/O.
        with self.condition:
            if self.halted or self.closing:
                raise AdmissionError("Queue requires cleanup or is shutting down", 503)
            if len(self.pending) + len(self.preparing) + int(self.running is not None) >= 3:
                raise AdmissionError("Global queue capacity reached")
            ip = hashlib.sha256(client_ip.encode()).hexdigest()
            now = self.clock()
            with sqlite3.connect(self.admission_path, timeout=30) as connection:
                connection.execute("BEGIN IMMEDIATE")
                count = connection.execute(
                    "SELECT COUNT(*) FROM admissions WHERE ip=? AND created>?", (ip, now - 3600)
                ).fetchone()[0]
                if count >= 2:
                    raise AdmissionError("Two new run attempts per IP per hour are allowed")
                # Failed preparation still consumes admission: otherwise repeated
                # bad repositories bypass the limit on expensive outbound fetches.
                connection.execute("INSERT INTO admissions VALUES (?,?,?)", (run_id, ip, now))
            self.preparing.add(run_id)
        try:
            prepared = prepare()
        except BaseException:
            with self.condition:
                self.preparing.discard(run_id)
                self.condition.notify_all()
            raise
        with self.condition:
            self.preparing.discard(run_id)
            if self.halted or self.closing:
                self.condition.notify_all()
                raise AdmissionError("Queue stopped while source was being prepared", 503)
            self.store.create_run(
                run_id,
                status="queued",
                api_owner=owner,
                api_worker_finished=False,
                api_source=request,
                target=prepared.target,
                target_met=False,
                policy=prepared.policy.model_dump(),
                run_dir=str(self.run_root / run_id),
            )
            self.store.add_event(run_id, "run.queued", {"position": len(self.pending) + 1})
            self.pending.append((run_id, prepared))
            position = len(self.pending)
            self.condition.notify_all()
            return position

    def _supervised(self, run_id, request):
        process = multiprocessing.get_context("spawn").Process(
            target=_process_entry,
            args=(
                self.worker,
                request.model_dump(),
                str(self.store.path),
                str(self.run_root),
                run_id,
            ),
            daemon=True,
        )
        process.start()
        self.store.update_run(run_id, api_worker_pid=process.pid)
        deadline = time.monotonic() + self.deadline
        while process.is_alive() and time.monotonic() < deadline and not self.closing:
            process.join(min(0.1, max(0, deadline - time.monotonic())))
        timed_out = process.is_alive() and not self.closing
        stopped = process.is_alive()
        if stopped:
            process.terminate()
            process.join(self.grace)
            if process.is_alive():
                process.kill()
                process.join(5)
        if process.is_alive():
            return False
        cleaned = cleanup_owned_lab(self.run_root, run_id)
        if timed_out:
            self.store.update_run(
                run_id,
                status="timeout",
                target_met=False,
                reason="Run exceeded its wall-clock deadline",
                api_cleanup_verified=cleaned,
            )
            self.store.add_event(
                run_id, "run.failed", {"reason": "deadline_exceeded", "cleanup_verified": cleaned}
            )
        elif stopped:
            self.store.update_run(
                run_id,
                status="cancelled",
                target_met=False,
                reason="Server shutdown cancelled the worker",
            )
            self.store.add_event(
                run_id, "run.failed", {"reason": "server_shutdown", "cleanup_verified": cleaned}
            )
        elif process.exitcode != 0:
            self.store.update_run(
                run_id, status="failed", target_met=False, reason="Worker exited unexpectedly"
            )
            self.store.add_event(
                run_id, "run.failed", {"reason": "worker_exit", "cleanup_verified": cleaned}
            )
        if not cleaned:
            self.store.update_run(
                run_id,
                status="needs_human",
                target_met=False,
                reason="Owned-container cleanup could not be verified",
                api_cleanup_verified=False,
            )
            self.store.add_event(run_id, "needs_human", {"reason": "cleanup_unverified"})
        directory = job_directory(self.run_root, run_id)
        if timed_out or stopped or process.exitcode != 0 or not cleaned:
            directory.mkdir(parents=True, exist_ok=True)
            # Regenerate the partial report from persisted evidence after cancellation;
            # do not preserve a stale success report after a forced termination.
            generate_report(
                directory,
                self.store.get_run(run_id),
                rounds=self.store.rounds(run_id),
                usage=self.store.usage(run_id),
            )
        return cleaned

    def _loop(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closing or (self.pending and not self.halted))
                if self.closing:
                    return
                run_id, request = self.pending.popleft()
                self.running = run_id
            cleaned = False
            self.store.update_run(run_id, status="running")
            try:
                if self.mode == "process":
                    cleaned = self._supervised(run_id, request)
                else:
                    result = self.worker(
                        request, store=self.store, run_root=self.run_root, run_id=run_id
                    )
                    _finish_result(self.store, run_id, result)
                    cleaned = True
            except Exception:  # noqa: BLE001 - preserve failed worker state and halt unsafe scheduling
                self.store.update_run(
                    run_id, status="failed", target_met=False, reason="Queue worker failed"
                )
                self.store.add_event(run_id, "run.failed", {"reason": "queue_worker_error"})
            finally:
                self.store.update_run(
                    run_id, api_worker_finished=cleaned, api_cleanup_verified=cleaned
                )
                with self.condition:
                    self.running = None
                    self.halted = not cleaned
                    self.condition.notify_all()

    def close(self):
        with self.condition:
            self.closing = True
            for run_id, _ in self.pending:
                self.store.update_run(
                    run_id,
                    status="needs_human",
                    api_worker_finished=True,
                    reason="Server stopped before queued run started",
                )
                self.store.add_event(run_id, "needs_human", {"reason": "server_shutdown"})
            self.pending.clear()
            self.condition.notify_all()
        self.thread.join(timeout=self.grace + 7 if self.mode == "process" else 1)
