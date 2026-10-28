"""Snapshot-only queue: metadata registry, isolated workers and bounded retention."""

from __future__ import annotations

import ctypes
import fcntl
import multiprocessing
import os
import shutil
import signal
import sqlite3
import stat
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager, nullcontext
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from headroom.api.security import RUN_ID, open_regular

RETENTION_SECONDS = 24 * 60 * 60
ACTIVE = ("receiving", "queued", "running")
TERMINAL = {"completed", "failed", "timeout", "cancelled", "budget_exceeded", "needs_human"}


class SnapshotAdmissionError(ValueError):
    def __init__(self, message, status=429):
        super().__init__(message)
        self.status = status


def directory_fd(path, *, create=False):
    """Open every ancestor with NOFOLLOW; never resolve away traversal or symlinks."""
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("Parent traversal is not allowed")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            if create:
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _child_entry(
    worker, request_values, run_root, run_id, channel, parent_pid, allocation_binding=None
):
    """Run only trusted diagnosis code; uploaded input is never imported or executed."""
    os.setsid()
    os.umask(0o077)

    # A lost API process must not leave a model worker consuming allowance.
    def parent_lost(_signal=None, _frame=None):
        os.killpg(os.getpid(), signal.SIGKILL)

    signal.signal(signal.SIGUSR1, parent_lost)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGUSR1, 0, 0, 0) != 0:
        os._exit(1)
    if os.getppid() != parent_pid:
        parent_lost()
    channel.send("ready")
    if channel.recv() != "proceed":
        return
    status = "failed"
    try:
        job = Path(run_root) / run_id
        descriptor = directory_fd(job)
        try:
            log = os.open(
                "worker.log",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=descriptor,
            )
        finally:
            os.close(descriptor)
        os.dup2(log, 1)
        os.dup2(log, 2)
        os.close(log)
        values = {
            key: Path(value) if key != "budget_usd" and value is not None else value
            for key, value in request_values.items()
        }
        allocation_context = nullcontext()
        if allocation_binding is not None:
            from headroom.acceptance.snapshot_binding import snapshot_feature_context

            allocation_context = snapshot_feature_context(
                allocation_binding, project_root=Path(run_root).parent.parent
            )
        with allocation_context:
            if worker is None:
                from headroom.snapshot_diagnosis import (
                    SnapshotDiagnosisRequest,
                    run_snapshot_diagnosis,
                )

                request = SnapshotDiagnosisRequest(**values)
                result = run_snapshot_diagnosis(request, run_root=Path(run_root), run_id=run_id)
            else:
                # Explicit offline test workers receive the same attribute contract.
                result = worker(SimpleNamespace(**values), run_root=Path(run_root), run_id=run_id)
        if isinstance(result, dict) and result.get("status") in TERMINAL:
            status = result["status"]
    except Exception:  # noqa: BLE001 - contain provider failures without exposing private data
        # Exception details stay out of both registry and API responses.
        status = "failed"
    finally:
        try:
            channel.send(status)
        except (BrokenPipeError, EOFError, OSError):
            pass
        channel.close()
        # Keep the owned process-group leader alive until its supervisor kills
        # the group, including descendants, without any PID-reuse window.
        while True:
            signal.pause()


def _group_running(group):
    """Check only the owned Linux session; zombies cannot run or make model calls."""
    try:
        for path in Path("/proc").iterdir():
            if not path.name.isdigit():
                continue
            try:
                fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
            except FileNotFoundError:
                continue
            if int(fields[2]) == group and int(fields[3]) == group and fields[0] != "Z":
                return True
        return False
    except (OSError, ValueError, IndexError):
        return True


class SnapshotQueue:
    def __init__(
        self, settings, *, worker: Callable | None = None, clock=time.time, allocation_parent=None
    ):
        self.settings = settings
        self.root = Path(settings.project_root) / "runs" / "uploads"
        self.registry = Path(settings.project_root) / ".cache" / "snapshot-admissions.sqlite3"
        self.worker = worker
        self.allocation = None
        if allocation_parent is not None:
            from headroom.acceptance.snapshot_binding import SnapshotWebAllocation

            self.allocation = SnapshotWebAllocation(
                allocation_parent, project_root=settings.project_root
            )
            if str(Path(settings.runtime_profile or "").absolute()) != self.allocation.profile_path:
                raise ValueError("Snapshot server profile differs from its private allocation")
        self.clock = clock
        self.deadline = min(float(settings.deadline_seconds), 480.0)
        allowance = Decimal(str(settings.public_run_budget))
        if not allowance.is_finite() or not Decimal(0) < allowance <= Decimal("0.30"):
            raise ValueError("Snapshot allowance must be positive and at most 0.30 USD")
        if not 0 < self.deadline <= 480:
            raise ValueError("Snapshot deadline must be positive and at most 480 seconds")
        self.allowance = str(allowance)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._started = False
        self._process_jobs = False
        self._lock_handle = None
        self.thread = None
        self.expiry_thread = None

    @property
    def submissions_available(self):
        """Whether this instance owns an active snapshot dispatcher."""
        # start() holds this lock until Thread.start() has completed, so a config
        # request cannot observe the interval between setup and worker startup.
        with self._lock:
            return bool(
                self._started
                and self._process_jobs
                and self._lock_handle is not None
                and not self._stop.is_set()
                and self.thread is not None
                and self.thread.is_alive()
            )

    @contextmanager
    def _connect(self, *, read_only=False):
        descriptor = directory_fd(self.registry.parent)
        try:
            # Closing a raw fd for an active SQLite inode releases every
            # POSIX advisory lock this process holds on that inode.
            info = os.stat(self.registry.name, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Invalid snapshot registry")
        finally:
            os.close(descriptor)
        target = self.registry.absolute().as_uri() + "?mode=ro" if read_only else self.registry
        db = sqlite3.connect(target, timeout=5, uri=read_only)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def start(self, *, process_jobs=True):
        """Own retention and optionally dispatch; return False if another instance owns it."""
        with self._lock:
            if self._started:
                return True
            root_fd = directory_fd(self.root, create=True)
            os.close(root_fd)
            data_fd = directory_fd(self.registry.parent, create=True)
            try:
                self._lock_handle = os.open(
                    "snapshot-manager.lock",
                    os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=data_fd,
                )
                try:
                    fcntl.flock(self._lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    os.close(self._lock_handle)
                    self._lock_handle = None
                    return False
                # Only raw-open a brand-new inode. An existing registry may
                # already have SQLite readers in this process.
                try:
                    descriptor = os.open(
                        self.registry.name,
                        os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=data_fd,
                    )
                except FileExistsError:
                    pass  # _connect validates existing entries without opening a raw fd.
                else:
                    os.close(descriptor)
                with self._connect() as db:
                    db.execute(
                        "CREATE TABLE IF NOT EXISTS snapshots("
                        "id TEXT PRIMARY KEY,owner TEXT NOT NULL,ip TEXT NOT NULL,"
                        "created_at REAL NOT NULL,status TEXT NOT NULL)"
                    )
                    db.execute(
                        "UPDATE snapshots SET status='failed' "
                        "WHERE status IN ('receiving','queued','running')"
                    )
                self.cleanup()
                self._stop.clear()
                self._started = True
                self._process_jobs = process_jobs is True
                self.thread = (
                    threading.Thread(target=self._loop, name="snapshot-queue", daemon=True)
                    if self._process_jobs
                    else None
                )
                self.expiry_thread = threading.Thread(
                    target=self._expiry_loop, name="snapshot-retention", daemon=True
                )
                if self.thread:
                    self.thread.start()
                self.expiry_thread.start()
                return True
            except BaseException:
                if self._lock_handle is not None:
                    os.close(self._lock_handle)
                    self._lock_handle = None
                raise
            finally:
                os.close(data_fd)

    def close(self):
        with self._lock:
            if not self._started:
                return
            self._stop.set()
            self._wake.set()
        if self.thread:
            self.thread.join(4)
        if self.expiry_thread:
            self.expiry_thread.join(2)
        with self._lock:
            if (self.thread and self.thread.is_alive()) or (
                self.expiry_thread and self.expiry_thread.is_alive()
            ):
                # Keep the single-manager lock if worker shutdown is not proven.
                raise RuntimeError("Snapshot worker did not stop")
            with self._connect() as db:
                db.execute(
                    "UPDATE snapshots SET status='cancelled' "
                    "WHERE status IN ('receiving','queued','running')"
                )
            self._started = False
            self._process_jobs = False
            if self._lock_handle is not None:
                os.close(self._lock_handle)
                self._lock_handle = None

    def reserve(self, owner, ip, *, judge=False):
        with self._lock:
            if not self._started or not self._process_jobs or self._stop.is_set():
                raise SnapshotAdmissionError("Snapshot service is unavailable", 503)
            now = self.clock()
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                count = db.execute(
                    "SELECT count(*) FROM snapshots "
                    "WHERE status IN ('receiving','queued','running')"
                ).fetchone()[0]
                if count >= 3:
                    raise SnapshotAdmissionError("Snapshot queue is full")
                if not judge:
                    recent = db.execute(
                        "SELECT count(*) FROM snapshots WHERE ip=? AND created_at>?",
                        (ip, now - 3600),
                    ).fetchone()[0]
                    if recent >= 2:
                        raise SnapshotAdmissionError("Two snapshot uploads per hour are allowed")
                identifier = uuid4().hex
                descriptor = directory_fd(self.root)
                try:
                    os.mkdir(identifier, 0o700, dir_fd=descriptor)
                finally:
                    os.close(descriptor)
                db.execute(
                    "INSERT INTO snapshots VALUES(?,?,?,?,?)",
                    (identifier, owner, ip, now, "receiving"),
                )
            return identifier, now

    def finish_upload(self, identifier):
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM snapshots WHERE id=?", (identifier,)).fetchone()
            if (
                not self._started
                or self._stop.is_set()
                or row is None
                or row["status"] != "receiving"
            ):
                raise SnapshotAdmissionError("Snapshot service is unavailable", 503)
            if self.clock() >= row["created_at"] + self.deadline:
                db.execute("UPDATE snapshots SET status='timeout' WHERE id=?", (identifier,))
                raise SnapshotAdmissionError("Snapshot request deadline exceeded", 408)
            position = db.execute(
                "SELECT count(*) FROM snapshots WHERE status IN ('queued','running')"
            ).fetchone()[0]
            db.execute("UPDATE snapshots SET status='queued' WHERE id=?", (identifier,))
            self._wake.set()
            return position

    def fail_upload(self, identifier, *, timeout=False):
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE snapshots SET status=? WHERE id=? AND status='receiving'",
                ("timeout" if timeout else "failed", identifier),
            )

    def row_for_owner(self, identifier, owner):
        if not RUN_ID.fullmatch(identifier):
            return None
        try:
            with self._lock, self._connect(read_only=True) as db:
                row = db.execute(
                    "SELECT id,created_at,status FROM snapshots WHERE id=? AND owner=?",
                    (identifier, owner),
                ).fetchone()
        except (OSError, ValueError, sqlite3.Error):
            return None
        if row is None or self.clock() >= row["created_at"] + RETENTION_SECONDS:
            return None
        return dict(row)

    def cleanup(self):
        """Remove only owned 32-hex children, never descend through a symlink."""
        with self._lock:
            cutoff = self.clock() - RETENTION_SECONDS
            descriptor = directory_fd(self.root)
            try:
                with self._connect() as db:
                    recorded = {
                        row["id"]: row["created_at"]
                        for row in db.execute("SELECT id,created_at FROM snapshots")
                    }
                    for name in os.listdir(descriptor):
                        if not RUN_ID.fullmatch(name):
                            continue
                        info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                        created = recorded.get(name, info.st_mtime)
                        if created > cutoff:
                            continue
                        if stat.S_ISDIR(info.st_mode):
                            if not shutil.rmtree.avoids_symlink_attacks:
                                raise RuntimeError("Secure retention cleanup is unavailable")
                            shutil.rmtree(name, dir_fd=descriptor)
                        else:
                            os.unlink(name, dir_fd=descriptor)
                    db.execute("DELETE FROM snapshots WHERE created_at<=?", (cutoff,))
            finally:
                os.close(descriptor)

    def _expiry_loop(self):
        while not self._stop.wait(60):
            try:
                self.cleanup()
            except (OSError, ValueError, RuntimeError, sqlite3.Error):
                # Fail closed if the promised retention cannot be maintained.
                self._stop.set()
                self._wake.set()
                return

    def _loop(self):
        try:
            self._dispatch_loop()
        except Exception:  # noqa: BLE001 - fail closed if the scheduling boundary fails
            # No raw exception reaches API/state; unavailable queue rejects admission.
            self._stop.set()

    def _dispatch_loop(self):
        while not self._stop.is_set():
            with self._lock, self._connect() as db:
                row = db.execute(
                    "SELECT id,created_at FROM snapshots WHERE status='queued' "
                    "ORDER BY created_at LIMIT 1"
                ).fetchone()
                if row:
                    db.execute("UPDATE snapshots SET status='running' WHERE id=?", (row["id"],))
            if row:
                status = self._execute(row["id"], row["created_at"])
                with self._lock, self._connect() as db:
                    db.execute("UPDATE snapshots SET status=? WHERE id=?", (status, row["id"]))
            else:
                self._wake.wait(0.1)
                self._wake.clear()

    def _execute(self, identifier, created):
        remaining = created + self.deadline - self.clock()
        if remaining <= 0:
            return "timeout"
        values = {"budget_usd": self.allowance, "runtime_profile": self.settings.runtime_profile}
        job = self.root / identifier
        try:
            for key, name in (
                ("snapshot", "snapshot.pickle"),
                ("traceback", "traceback.txt"),
                ("source", "source.py"),
            ):
                try:
                    with open_regular(job, name):
                        pass
                    values[key] = str(job / name)
                except FileNotFoundError:
                    if key == "snapshot":
                        raise ValueError("Missing snapshot")
                    values[key] = None
        except (OSError, ValueError):
            return "failed"
        binding = None
        if self.allocation is not None:
            from headroom.snapshot_diagnosis import SnapshotDiagnosisRequest

            try:
                binding = self.allocation.claim(SnapshotDiagnosisRequest(**values), identifier)
            except (OSError, ValueError, TypeError, KeyError):
                return "failed"
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe()
        process = context.Process(
            target=_child_entry,
            args=(self.worker, values, str(self.root), identifier, sender, os.getpid(), binding),
            daemon=False,
        )
        deadline = time.monotonic() + max(0, created + self.deadline - self.clock())
        ready = False
        reported_terminal = False
        status = "failed"
        try:
            process.start()
            sender.close()
            while process.is_alive():
                if self._stop.is_set():
                    status = "cancelled"
                    break
                if time.monotonic() >= deadline:
                    status = "timeout"
                    break
                if receiver.poll(0.05):
                    message = receiver.recv()
                    if message == "ready" and not ready:
                        ready = True
                        receiver.send("proceed")
                    elif message in TERMINAL:
                        reported_terminal = True
                        status = message
                        break
        except (OSError, EOFError, RuntimeError, ValueError):
            status = "failed"
        finally:
            cleanup_verified = not process.pid
            if process.pid:
                try:
                    # A crashed leader can still leave a parser descendant in
                    # its owned session. Stop that group even after leader exit.
                    if ready:
                        os.killpg(process.pid, signal.SIGKILL)
                    elif process.is_alive():
                        process.kill()
                except ProcessLookupError:
                    pass
                process.join(1)
                cleanup_until = time.monotonic() + 1
                while ready and _group_running(process.pid) and time.monotonic() < cleanup_until:
                    time.sleep(0.01)
                cleanup_verified = not process.is_alive() and not (
                    ready and _group_running(process.pid)
                )
                if not cleanup_verified:
                    self._stop.set()
            receiver.close()
            sender.close()
            if binding is not None:
                try:
                    from headroom.acceptance.snapshot_binding import snapshot_cleanup_verified

                    cleanup_verified = cleanup_verified and snapshot_cleanup_verified(
                        self.root, identifier
                    )
                    settlement = self.allocation.finish(
                        binding,
                        execution_terminal=reported_terminal,
                        cleanup_verified=cleanup_verified,
                    )
                    if settlement.get("status") != "settled":
                        status = "failed"
                        self._stop.set()
                except Exception:  # noqa: BLE001 -- unknown settlement blocks further dispatch
                    status = "failed"
                    self._stop.set()
        return status
