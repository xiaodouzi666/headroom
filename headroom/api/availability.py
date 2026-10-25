"""Read-only service observations. Never loads credentials or performs inference."""

import copy
import os
import sqlite3
import stat
import subprocess
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from pathlib import Path

import httpx

from headroom.budget import money
from headroom.config import OFFICIAL_BASE_URLS
from headroom.ledger_path import (
    LedgerPathError,
    require_initialized_ledger,
    select_budget_database,
    validate_existing_ledger_path,
)
from headroom.runtime import RuntimeNotReady, read_live_profile


def timestamp():
    return datetime.now(UTC).isoformat()


def probe_gpu():
    """Query driver metadata only; no CUDA context, allocation or user workload."""
    try:
        values = (
            subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.free,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=1,
                check=True,
            )
            .stdout.strip()
            .splitlines()
        )
        devices = []
        for line in values:
            free, total = (int(part.strip()) for part in line.split(","))
            if not 0 <= free <= total or total <= 0:
                raise ValueError
            devices.append({"free_mib": free, "total_mib": total})
        if not devices:
            raise ValueError
        processes = (
            subprocess.run(
                ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=1,
                check=True,
            )
            .stdout.strip()
            .splitlines()
        )
        if any(not row.strip().isdigit() for row in processes):
            raise ValueError
        busy = bool(processes)
        return {
            "status": "busy" if busy else "available",
            "available": not busy,
            "busy": busy,
            "device_count": len(devices),
            "devices": devices,
            "compute_process_count": len(processes),
            "checked_at": timestamp(),
        }
    except FileNotFoundError:
        return {
            "status": "unavailable",
            "available": False,
            "busy": None,
            "checked_at": timestamp(),
            "reason": "driver_tool_unavailable",
        }
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return {
            "status": "unknown",
            "available": None,
            "busy": None,
            "checked_at": timestamp(),
            "reason": "driver_query_failed",
        }


def probe_provider(base_url):
    """Unauthenticated, bounded GET headers; reachability is not model access."""
    if base_url not in OFFICIAL_BASE_URLS:
        return {
            "status": "unknown",
            "reachable": None,
            "authentication_checked": False,
            "checked_at": timestamp(),
            "reason": "endpoint_not_allowlisted",
        }
    try:
        with (
            httpx.Client(timeout=2, follow_redirects=False, trust_env=False) as client,
            client.stream("GET", base_url + "models") as response,
        ):
            status = response.status_code
        return {
            "status": "reachable" if status in {200, 401, 403} else "degraded",
            "reachable": True,
            "http_status": status,
            "authentication_checked": False,
            "checked_at": timestamp(),
        }
    except (httpx.HTTPError, OSError):
        return {
            "status": "unreachable",
            "reachable": False,
            "authentication_checked": False,
            "checked_at": timestamp(),
            "reason": "connection_failed",
        }


def read_local_budget(
    path, *, daily_limit, total_limit, day=None, require_existing=False, expected_identity=None
):
    """Read consistent ledger rows without creating databases/tables or write locks."""
    result = {
        "scope": "local_application_authorization",
        "account_balance": None,
        "checked_at": timestamp(),
        "status": "unknown",
        "remaining_usd": None,
        "note": "Local reservations only; not provider balance or a billing guarantee. "
        "Actual charges may exceed local estimates.",
    }
    try:
        daily, total = money(daily_limit), money(total_limit)
        today = day or datetime.now(UTC).date().isoformat()
        path = (
            require_initialized_ledger(path, expected_identity=expected_identity)
            if require_existing
            else Path(path)
        )
        initialized = path.exists()
        runs, attempts = [], []
        if initialized:
            if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
                raise ValueError
            conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.05)
            until = time.monotonic() + 0.5
            try:
                if require_existing:
                    validate_existing_ledger_path(path, expected_identity=expected_identity)
                conn.set_progress_handler(lambda: int(time.monotonic() >= until), 1000)
                conn.execute("PRAGMA query_only=ON")
                conn.execute("BEGIN")
                runs = conn.execute(
                    "SELECT id,day,limit_usd,status,halt_reason FROM budget_runs LIMIT 100001"
                ).fetchall()
                columns = {row[1] for row in conn.execute("PRAGMA table_info(budget_attempts)")}
                charge_status = "charge_status" if "charge_status" in columns else "NULL"
                admission = "admission_kind" if "admission_kind" in columns else "NULL"
                upper = "upper_usd" if "upper_usd" in columns else "NULL"
                attempts = conn.execute(
                    "SELECT run_id,charged_usd,actual_usd,settled,"
                    + charge_status
                    + ","
                    + upper
                    + ","
                    + admission
                    + " FROM budget_attempts LIMIT 100001"
                ).fetchall()
                if len(runs) > 100000 or len(attempts) > 100000:
                    raise ValueError
            finally:
                conn.close()
        elif path.is_symlink():
            raise ValueError
        run_ids = {row[0] for row in runs}
        charged = {}
        unknown = pending = bounded = reviewed = 0
        with localcontext() as context:
            context.prec = 256
            known = Decimal(0)
            for run_id, charge, actual, settled, charge_status, upper, admission in attempts:
                if (
                    run_id not in run_ids
                    or settled not in {0, 1}
                    or (not settled and actual is not None)
                ):
                    raise ValueError
                charged[run_id] = charged.get(run_id, Decimal(0)) + money(charge)
                if actual is None:
                    unknown += 1
                    if charge_status in {"upper_bound", "reviewed_retained"}:
                        if (
                            not settled
                            or admission != "verified_provider_bound"
                            or money(charge) > money(upper)
                        ):
                            raise ValueError
                        if charge_status == "reviewed_retained" and money(charge) != money(upper):
                            raise ValueError
                        bounded += charge_status == "upper_bound"
                        reviewed += charge_status == "reviewed_retained"
                else:
                    known += money(actual)
                pending += not settled
            committed = committed_today = Decimal(0)
            halted = False
            for run_id, run_day, limit, status, halt in runs:
                if status not in {"open", "closed"}:
                    raise ValueError
                used = charged.get(run_id, Decimal(0))
                held = max(money(limit), used) if status == "open" else used
                committed += held
                if run_day == today:
                    committed_today += held
                halted |= halt is not None
            total_remaining = max(Decimal(0), total - committed)
            daily_remaining = max(Decimal(0), daily - committed_today)
            remaining = min(total_remaining, daily_remaining)
            conservative = sum(charged.values(), Decimal(0))
        unresolved = unknown - bounded - reviewed
        billing_complete = not halted and unresolved == 0 and pending == 0
        result.update(
            status="billing_review_required"
            if halted or unresolved > pending
            else "pending_charge"
            if pending
            else "exhausted"
            if remaining == 0
            else "available",
            remaining_usd=str(remaining),
            daily_remaining_usd=str(daily_remaining),
            authorized_remaining_usd=str(total_remaining),
            daily_limit_usd=str(daily),
            authorized_total_usd=str(total),
            committed_usd=str(committed),
            known_charge_usd=str(known),
            total_actual_usd=None if unknown else str(known),
            unknown_attempts=unknown,
            settled_unknown_attempts=unknown - pending,
            bounded_attempts=bounded,
            reviewed_retained_attempts=reviewed,
            unresolved_attempts=unresolved,
            billing_complete=billing_complete,
            conservative_total_usd=str(conservative) if billing_complete else None,
            pending_attempts=pending,
            billing_bound_unresolved=halted,
            dispatch_blocked=halted or bool(unresolved) or bool(pending),
            ledger_initialized=initialized,
        )
    except (OSError, sqlite3.Error, ValueError, TypeError, ArithmeticError):
        result["reason"] = "local_budget_unavailable"
    return result


class AvailabilityMonitor:
    """Refresh bounded external probes off the request thread; serve timestamped cache."""

    def __init__(
        self,
        settings,
        *,
        enabled=True,
        gpu_probe=None,
        provider_probe=None,
        profile_loader=None,
        clock=time.monotonic,
        ttl=15,
        waiter=None,
    ):
        self.settings = settings
        self.enabled = enabled
        self.gpu_probe = gpu_probe or probe_gpu
        self.provider_probe = provider_probe or probe_provider
        self.profile_loader = profile_loader or read_live_profile
        self.clock = clock
        self.ttl = ttl
        self.refresh_interval = ttl / 3
        self.waiter = waiter or (lambda stop, seconds: stop.wait(seconds))
        self.stop = threading.Event()
        self.endpoint = OFFICIAL_BASE_URLS[0]
        self.refreshing = False
        self.lock = threading.Lock()
        self.thread = None
        self.closed = False
        try:
            self.budget_database = select_budget_database(settings.project_root)
        except LedgerPathError:
            self.budget_database = None
        self.observed_at = {"gpu": None, "token_factory": None}
        self.gpu = {"status": "unknown", "available": None, "busy": None, "checked_at": None}
        self.provider = {
            "status": "unknown",
            "reachable": None,
            "checked_at": None,
            "authentication_checked": False,
        }

    def configuration(self):
        try:
            profile = self.profile_loader(
                self.settings.runtime_profile
                or self.settings.project_root / ".cache/tokenfactory-runtime.json"
            )
        except (RuntimeNotReady, OSError, ValueError):
            profile = None
        return profile

    def refresh(self, base_url):
        with self.lock:
            self.endpoint = base_url
            if not self.enabled or self.closed or (self.thread and self.thread.is_alive()):
                return
            self.thread = threading.Thread(target=self._poll, name="headroom-health", daemon=True)
            self.thread.start()

    def _poll(self):
        # Refresh before expiry independently of HTTP polling. Matching a
        # browser's polling period must never make every response stale.
        try:
            while not self.stop.is_set():
                with self.lock:
                    base_url = self.endpoint
                    self.refreshing = True
                for name, probe, args, unknown in (
                    (
                        "gpu",
                        self.gpu_probe,
                        (),
                        {"status": "unknown", "available": None, "busy": None},
                    ),
                    (
                        "token_factory",
                        self.provider_probe,
                        (base_url,),
                        {"status": "unknown", "reachable": None, "authentication_checked": False},
                    ),
                ):
                    if self.stop.is_set():
                        return
                    try:
                        observation = probe(*args)
                    except Exception:  # noqa: BLE001 - redact external diagnostics.
                        observation = {
                            **unknown,
                            "checked_at": timestamp(),
                            "reason": "probe_failed",
                        }
                    with self.lock:
                        if self.closed:
                            return
                        if name == "gpu":
                            self.gpu = observation
                        else:
                            self.provider = observation
                        self.observed_at[name] = self.clock()
                with self.lock:
                    self.refreshing = False
                if self.waiter(self.stop, self.refresh_interval):
                    return
        finally:
            with self.lock:
                self.refreshing = False

    def snapshot(self):
        profile = self.configuration()
        configured = self.settings.runtime_configured or profile is not None
        endpoint = profile.base_url if profile is not None else OFFICIAL_BASE_URLS[0]
        self.refresh(endpoint)
        with self.lock:
            gpu, provider = copy.deepcopy(self.gpu), copy.deepcopy(self.provider)
            observed_at = self.observed_at.copy()
            refreshing = self.refreshing
        for name, value in (("gpu", gpu), ("token_factory", provider)):
            observed = observed_at[name]
            stale = observed is None or self.clock() - observed >= self.ttl
            value["stale"] = stale
            value["refreshing"] = refreshing
            if stale:
                value["status"] = "unknown"
                if "available" in value:
                    value["available"], value["busy"] = None, None
                if "reachable" in value:
                    value["reachable"] = None
        provider.update(
            configured=configured,
            configuration_scope="reviewed_runtime_profile",
            authentication_checked=False,
        )
        budget = {
            "status": "unknown",
            "scope": "local_application_authorization",
            "account_balance": None,
            "remaining_usd": None,
            "checked_at": timestamp(),
            "reason": "runtime_profile_unavailable",
        }
        if profile is not None:
            try:
                if self.budget_database is None:
                    raise LedgerPathError("Shared budget database selection is unavailable")
                daily = min(money("12"), money(os.environ.get("HEADROOM_DAILY_BUDGET_USD", "12")))
                budget = read_local_budget(
                    self.budget_database.path,
                    require_existing=self.budget_database.require_existing,
                    expected_identity=self.budget_database.file_identity,
                    daily_limit=daily,
                    total_limit=profile.authorized_total_usd,
                )
            except LedgerPathError:
                budget["reason"] = "invalid_shared_budget_ledger"
            except (ValueError, TypeError, ArithmeticError):
                budget["reason"] = "invalid_local_budget_limit"
        return {"gpu": gpu, "token_factory": provider, "local_budget": budget}

    def close(self):
        with self.lock:
            self.closed = True
            self.stop.set()
            thread = self.thread
        if thread is not None and thread is not threading.current_thread():
            # Wake scheduled waits immediately; bounded probes already in flight
            # finish without scheduling another request.
            thread.join(timeout=5)
