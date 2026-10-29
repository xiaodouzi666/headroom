"""One scheduler thread; production jobs run in supervised spawn processes."""

import ctypes
import hashlib
import json
import multiprocessing
import os
import re
import signal
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


def _bound_worker(funding_kind):
    if funding_kind == "judge":
        from headroom.acceptance.judge_binding import run_bound_judge

        return run_bound_judge
    if funding_kind == "demo":
        from headroom.acceptance.demo_binding import run_bound_demo

        return run_bound_demo
    raise ValueError("Unknown trusted funding kind")


def _process_entry(
    worker, request, store_path, run_root, run_id, deadline, demo_binding=None, funding_kind="demo"
):
    store = Store(store_path)
    try:
        if time.monotonic() >= deadline:
            store.update_run(
                run_id, status="timeout", target_met=False, reason="queue_deadline_exceeded"
            )
            store.add_event(run_id, "run.failed", {"reason": "queue_deadline_exceeded"})
            return
        if funding_kind == "judge" and demo_binding is None:
            raise ValueError("Judge execution requires its trusted allocation binding")
        parsed = FixRequest.model_validate(request)
        if demo_binding is not None:
            result = _bound_worker(funding_kind)(
                parsed,
                store=store,
                run_root=Path(run_root),
                run_id=run_id,
                binding=demo_binding,
                worker=worker,
            )
        else:
            result = (worker or run_fix)(
                parsed, store=store, run_root=Path(run_root), run_id=run_id
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


def _arm_preparation_parent_death(parent_pid):
    """Linux parent-death notification also kills this session's Git descendants."""

    def parent_lost(_signal=None, _frame=None):
        os.killpg(os.getpid(), signal.SIGKILL)

    signal.signal(signal.SIGUSR1, parent_lost)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGUSR1, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        raise OSError(ctypes.get_errno(), "Cannot supervise source preparation parent death")
    # Parent death before prctl is not delivered retroactively.
    if os.getppid() != parent_pid:
        parent_lost()


def _prepare_entry(prepare, deadline, sender, parent_pid):
    """Data-only preparation in an owned session, never the model/GPU worker."""
    os.setsid()
    _arm_preparation_parent_death(parent_pid)
    os.environ.clear()
    os.environ.update(HOST_ENV)
    try:
        sender.send(("ready", None))
        if sender.recv() != "proceed":
            raise TimeoutError
        if time.monotonic() >= deadline:
            raise TimeoutError
        request = prepare(deadline=deadline)
        if time.monotonic() >= deadline:
            raise TimeoutError
        sender.send(("result", request.model_dump()))
    except TimeoutError:
        sender.send(("timeout", None))
    except Exception:  # noqa: BLE001 - no source text, credentials or private errors on the pipe
        sender.send(("error", None))
    finally:
        sender.close()
        # Keep the owned session leader alive until its supervisor kills the
        # group, including after success/error. Its PID cannot be reused first.
        while True:
            signal.pause()


def _preparation_identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19], int(fields[2]), int(fields[3])
    except (OSError, ValueError, IndexError):
        return None


def _preparation_group_alive(group):
    """Linux-only verification of this owned process group, ignoring reaped zombies."""
    try:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            except FileNotFoundError:
                continue
            if int(fields[2]) == group and fields[0] != "Z":
                return True
        return False
    except (OSError, ValueError, IndexError):
        return True


def _stop_preparation(process, identity, ready):
    # Match the exact owned process, not merely a possibly reused numeric PID.
    current = _preparation_identity(process.pid)
    if identity is None or current is None or current[0] != identity[0]:
        process.join(0)
        return not process.is_alive() and not _preparation_group_alive(process.pid)
    try:
        if current[1:] == (process.pid, process.pid):
            os.killpg(process.pid, signal.SIGKILL)
        elif ready:
            return False
        else:
            # Before the handshake, the child cannot launch Git or touch source.
            process.kill()
    except ProcessLookupError:
        pass
    except OSError:
        return False
    process.join(1)
    until = time.monotonic() + 1
    while _preparation_group_alive(process.pid) and time.monotonic() < until:
        time.sleep(0.01)
    return not process.is_alive() and not _preparation_group_alive(process.pid)


def cleanup_owned_lab(run_root, run_id):
    """Remove only this job's verified target and labelled artifact store."""
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
                # Store creation follows the host manifest, never target source copying.
                continue
            with open_regular(item, "manifest.json", 2 * 1024 * 1024) as handle:
                manifest = json.load(handle)
            if manifest.get("image") != docker.IMAGE or not isinstance(
                manifest.get("command"), list
            ):
                return False
            name = "headroom-lab-" + item.name
            store = manifest.get("owned_artifact_store")
            if store is None:
                store = docker.artifact_volume.discover_store(name, output_path=item / "artifacts")
            if store is not None and (
                store.get("target") != name
                or store.get("output_path") != str(item / "artifacts")
                or store.get("volume") != docker.artifact_volume.names(name)["volume"]
            ):
                return False
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
                if not (
                    ("no such object" in message or "no such container" in message)
                    and name in message
                ):
                    return False
            else:
                details = json.loads(inspected.stdout)[0]
                mounts = {m.get("Destination"): m for m in details.get("Mounts", [])}
                output_mount = mounts.get("/out", {})
                if details.get("Name") != "/" + name or mounts.get("/source", {}).get(
                    "Source"
                ) != str(item / "source"):
                    return False
                if store is None:
                    if output_mount.get("Source") != str(item / "artifacts"):
                        return False
                elif (
                    output_mount.get("Type") != "volume"
                    or output_mount.get("Name") != store["volume"]
                    or details.get("Image") != store["image_id"]
                    or output_mount.get("RW") is not True
                    or mounts.get("/source", {}).get("RW") is not False
                    or (
                        manifest.get("owned_target_id") is not None
                        and details.get("Id") != manifest["owned_target_id"]
                    )
                ):
                    return False
                container_id = details.get("Id", "")
                if not re.fullmatch(r"[0-9a-f]{64}", container_id):
                    return False
                if not docker.cleanup_container(container_id).get("cleanup_verified"):
                    return False
            if store is not None and not docker.artifact_volume.cleanup_store(store).get(
                "cleanup_verified"
            ):
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
        hourly_limit=2,
        demo_allocation=None,
        judge_allocation=None,
    ):
        self.store, self.run_root = store, Path(run_root)
        self.worker, self.mode = worker, mode
        self.demo_allocation = demo_allocation
        self.judge_allocation = judge_allocation
        self.deadline, self.grace, self.clock = deadline, grace, clock
        if type(hourly_limit) is not int or hourly_limit < 1:
            raise ValueError("Hourly run limit must be a positive integer")
        self.hourly_limit = hourly_limit
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
            # Preserve every legacy admission and its original conservative quota
            # treatment. Only new, server-selected judge runs get an exemption.
            connection.execute(
                "CREATE TABLE IF NOT EXISTS hourly_exempt_admissions (run_id TEXT PRIMARY KEY)"
            )
        self.thread = threading.Thread(target=self._loop, name="headroom-api-queue", daemon=True)
        self.expiry_thread = threading.Thread(
            target=self._expiry_loop, name="headroom-api-expiry", daemon=True
        )

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
        self.expiry_thread.start()

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

    def _finish_unstarted(self, run_id, *, reason, cleanup_verified=True, status="timeout"):
        self.store.update_run(
            run_id,
            status=status if cleanup_verified else "needs_human",
            target_met=False,
            reason=reason,
            api_worker_finished=False,
            api_cleanup_verified=cleanup_verified,
            api_report_pending=True,
            api_report_ready=False,
        )
        self.store.add_event(
            run_id,
            "run.failed" if cleanup_verified else "needs_human",
            {"reason": reason, "cleanup_verified": cleanup_verified},
        )
        ready, error = False, None
        try:
            directory = job_directory(self.run_root, run_id)
            directory.mkdir(parents=True, exist_ok=True)
            generate_report(
                directory, self.store.get_run(run_id), rounds=[], usage=self.store.usage(run_id)
            )
            ready = True
        except Exception:  # noqa: BLE001 - keep expiry alive and expose a safe terminal failure
            error = "partial_report_generation_failed"
            self.store.update_run(
                run_id,
                status="needs_human",
                reason="Partial report generation failed; retained evidence requires review",
            )
            self.store.add_event(run_id, "needs_human", {"reason": error})
        finally:
            self.store.update_run(
                run_id,
                api_report_pending=False,
                api_report_ready=ready,
                api_report_error=error,
                api_worker_finished=cleanup_verified,
            )

    def _prepare(self, prepare, deadline):
        if self.mode == "thread":
            # Trusted in-process fixtures only. Production always uses spawn.
            return prepare(deadline=deadline), True
        receiver, sender = multiprocessing.get_context("spawn").Pipe(duplex=True)
        process = multiprocessing.get_context("spawn").Process(
            target=_prepare_entry, args=(prepare, deadline, sender, os.getpid()), daemon=True
        )
        result, outcome, identity, ready = None, None, None, False
        try:
            process.start()
            identity = _preparation_identity(process.pid)
            sender.close()
            while not self.closing and time.monotonic() < deadline:
                if receiver.poll(min(0.05, max(0, deadline - time.monotonic()))):
                    try:
                        kind, payload = receiver.recv()
                    except EOFError:
                        break
                    if kind == "ready":
                        ready = True
                        receiver.send("proceed")
                    else:
                        outcome = kind
                        result = payload
                        break

        except (OSError, EOFError):
            outcome = "error"
        finally:
            cleaned = (
                _stop_preparation(process, identity, ready) if process.pid is not None else True
            )
            sender.close()
            receiver.close()
        if not cleaned:
            with self.condition:
                self.halted = True
                self.condition.notify_all()
            raise AdmissionError("Source preparation cleanup could not be verified", 503)
        if self.closing:
            raise AdmissionError("Queue stopped while source was being prepared", 503)
        if outcome == "timeout" or time.monotonic() >= deadline:
            raise AdmissionError("Source preparation exceeded its admission deadline", 504)
        if outcome != "result":
            raise ValueError("Source preparation failed")
        return FixRequest.model_validate(result), cleaned

    def _expire_pending(self):
        expired = []
        with self.condition:
            retained = deque()
            for run_id, request, deadline in self.pending:
                if time.monotonic() >= deadline:
                    expired.append(run_id)
                else:
                    retained.append((run_id, request, deadline))
            self.pending = retained
        for run_id in expired:
            self._finish_unstarted(run_id, reason="queue_deadline_exceeded")

    def _expiry_loop(self):
        # Report rendering never runs in the active worker's deadline watchdog.
        while True:
            self._expire_pending()
            with self.condition:
                if self.closing:
                    return
                wait = min(
                    (max(0, item[2] - time.monotonic()) for item in self.pending),
                    default=None,
                )
                self.condition.wait(timeout=wait)

    def submit(self, run_id, request, owner, client_ip, prepare, *, funding_kind=None):
        # Only the API's authenticated server-side branch supplies this value.
        if funding_kind is None:
            funding_kind = "demo" if self.demo_allocation is not None else "default"
        allocations = {
            "default": None,
            "demo": self.demo_allocation,
            "judge": self.judge_allocation,
        }
        if funding_kind not in allocations or (
            funding_kind != "default" and allocations[funding_kind] is None
        ):
            raise AdmissionError("Selected execution allowance is unavailable", 503)
        if funding_kind == "judge" and not self.judge_allocation.available:
            raise AdmissionError("Selected execution allowance is unavailable", 503)
        # Admission starts one deadline shared by preparation, waiting and execution.
        # Upload/validation before admission and cleanup afterwards are separate.
        with self.condition:
            if self.halted or self.closing:
                raise AdmissionError("Queue requires cleanup or is shutting down", 503)
            if len(self.pending) + len(self.preparing) + int(self.running is not None) >= 3:
                raise AdmissionError("Global queue capacity reached")
            ip = hashlib.sha256(client_ip.encode()).hexdigest()
            now = self.clock()
            with sqlite3.connect(self.admission_path, timeout=30) as connection:
                connection.execute("BEGIN IMMEDIATE")
                if funding_kind != "judge":
                    count = connection.execute(
                        "SELECT COUNT(*) FROM admissions AS a WHERE a.ip=? AND a.created>? "
                        "AND NOT EXISTS (SELECT 1 FROM hourly_exempt_admissions AS e "
                        "WHERE e.run_id=a.run_id)",
                        (ip, now - 3600),
                    ).fetchone()[0]
                    if count >= self.hourly_limit:
                        raise AdmissionError(
                            f"At most {self.hourly_limit} new run attempt(s) per IP per hour"
                        )
                connection.execute("INSERT INTO admissions VALUES (?,?,?)", (run_id, ip, now))
                if funding_kind == "judge":
                    connection.execute("INSERT INTO hourly_exempt_admissions VALUES (?)", (run_id,))
            limit = self.deadline
            deadline = time.monotonic() + limit
            admitted_at = self.clock()
            self.preparing.add(run_id)

        def create_record():
            self.store.create_run(
                run_id,
                status="queued",
                api_owner=owner,
                api_funding_kind=funding_kind,
                api_worker_finished=False,
                api_source=request,
                target=request.get("target"),
                search_mode=request.get("search_mode"),
                policy=request.get("policy", {}),
                numerical_reference=request.get("numerical_reference"),
                allocator_conf=request.get("allocator_conf"),
                target_met=False,
                run_dir=str(self.run_root / run_id),
                api_admitted_at=admitted_at,
                api_deadline_at=admitted_at + limit,
                api_execution_limit_seconds=limit,
                api_cleanup_grace_seconds=self.grace,
            )

        try:
            try:
                prepared, _ = self._prepare(prepare, deadline)
            except AdmissionError as error:
                create_record()
                self._finish_unstarted(
                    run_id,
                    reason="preparation_deadline_exceeded"
                    if error.status == 504
                    else "preparation_cancelled",
                    cleanup_verified=not self.halted,
                    status="timeout" if error.status == 504 else "cancelled",
                )
                raise
            except TimeoutError:
                create_record()
                self._finish_unstarted(run_id, reason="preparation_deadline_exceeded")
                raise AdmissionError(
                    "Source preparation exceeded its admission deadline", 504
                ) from None
            with self.condition:
                if self.halted or self.closing:
                    raise AdmissionError("Queue stopped while source was being prepared", 503)
                create_record()
                if time.monotonic() >= deadline:
                    self._finish_unstarted(run_id, reason="preparation_deadline_exceeded")
                    raise AdmissionError("Source preparation exceeded its admission deadline", 504)
                self.store.update_run(
                    run_id,
                    target=prepared.target,
                    policy=prepared.policy.model_dump(),
                    numerical_reference=prepared.numerical_reference.model_dump(),
                    allocator_conf=prepared.allocator_conf,
                    search_mode=prepared.search_mode,
                )
                self.store.add_event(run_id, "run.queued", {"position": len(self.pending) + 1})
                self.pending.append((run_id, prepared, deadline))
                self.preparing.discard(run_id)
                position = len(self.pending)
                self.condition.notify_all()
                return position
        finally:
            with self.condition:
                self.preparing.discard(run_id)
                self.condition.notify_all()

    def _supervised(self, run_id, request, deadline, demo_binding=None, funding_kind="demo"):
        if time.monotonic() >= deadline:
            self._finish_unstarted(run_id, reason="queue_deadline_exceeded")
            return True
        process = multiprocessing.get_context("spawn").Process(
            target=_process_entry,
            args=(
                self.worker,
                request.model_dump(),
                str(self.store.path),
                str(self.run_root),
                run_id,
                deadline,
                demo_binding,
                funding_kind,
            ),
            daemon=True,
        )
        process.start()
        self.store.update_run(run_id, api_worker_pid=process.pid)
        while process.is_alive() and time.monotonic() < deadline and not self.closing:
            process.join(min(0.1, max(0, deadline - time.monotonic())))
        timed_out = not self.closing and (
            time.monotonic() >= deadline or self.store.get_run(run_id)["status"] == "timeout"
        )
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
                reason="Run exceeded its admission-to-execution deadline; cleanup is separate",
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
                if self.closing:
                    return
                if not self.pending or self.halted:
                    wait = min(
                        (max(0, item[2] - time.monotonic()) for item in self.pending), default=None
                    )
                    self.condition.wait(timeout=wait)
                    continue
                run_id, request, deadline = self.pending.popleft()
                self.running = run_id
            cleaned = False
            demo_binding = None
            allocation = None
            funding_kind = self.store.get_run(run_id).get(
                "api_funding_kind", "demo" if self.demo_allocation is not None else "default"
            )
            self.store.update_run(run_id, status="running")
            try:
                allocations = {
                    "default": None,
                    "demo": self.demo_allocation,
                    "judge": self.judge_allocation,
                }
                if funding_kind not in allocations or (
                    funding_kind != "default" and allocations[funding_kind] is None
                ):
                    cleaned = True
                    raise ValueError("Selected execution allowance is unavailable")
                allocation = allocations[funding_kind]
                if allocation is not None:
                    source_sha = (
                        self.store.get_run(run_id).get("api_source", {}).get("source_sha256")
                    )
                    # No model or GPU work precedes this durable allocation check.
                    cleaned = True
                    request, demo_binding = allocation.begin(
                        run_id, request, source_sha256=source_sha
                    )
                    cleaned = False
                    binding_field = (
                        "api_judge_binding" if funding_kind == "judge" else "api_demo_binding"
                    )
                    self.store.update_run(run_id, **{binding_field: demo_binding})
                if self.mode == "process":
                    cleaned = self._supervised(
                        run_id, request, deadline, demo_binding, funding_kind
                    )
                elif time.monotonic() >= deadline:
                    self._finish_unstarted(run_id, reason="queue_deadline_exceeded")
                    cleaned = True
                else:
                    if demo_binding is not None:
                        result = _bound_worker(funding_kind)(
                            request,
                            store=self.store,
                            run_root=self.run_root,
                            run_id=run_id,
                            binding=demo_binding,
                            worker=self.worker,
                        )
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
                accounting_ok = True
                if demo_binding is not None:
                    try:
                        accounting = allocation.finish(
                            demo_binding,
                            execution_terminal=self.store.get_run(run_id).get("status") in TERMINAL,
                            cleanup_verified=cleaned,
                        )
                        accounting_ok = accounting["status"] == "settled"
                    except Exception:  # noqa: BLE001 - retain active claim; fail closed
                        accounting_ok = False
                self.store.update_run(
                    run_id, api_worker_finished=cleaned, api_cleanup_verified=cleaned
                )
                with self.condition:
                    self.running = None
                    self.halted = self.halted or not cleaned or not accounting_ok
                    self.condition.notify_all()

    def close(self):
        with self.condition:
            self.closing = True
            for run_id, _, _ in self.pending:
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
        self.expiry_thread.join(timeout=1)
        until = time.monotonic() + self.grace + 3
        with self.condition:
            while self.preparing and time.monotonic() < until:
                self.condition.wait(timeout=max(0, until - time.monotonic()))
