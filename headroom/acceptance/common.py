"""Shared, explicit acceptance runtime lifecycle; preparation never invokes this context."""

import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import httpx

from headroom.api.security import open_regular
from headroom.budget import BudgetLedger, money
from headroom.runtime import PROJECT_ROOT, build_live_runtime, read_live_profile
from headroom.store.db import Store


def read_bytes(path, max_bytes):
    path = Path(path)
    if any(part.lower().startswith(".env") for part in path.parts):
        raise ValueError("Credential paths are not acceptance artifacts")
    with open_regular(path.parent, path.name, max_bytes=max_bytes) as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Artifact exceeds its bounded read limit")
    return raw


def read_json(path, max_bytes=2 * 1024 * 1024):
    def reject(value):
        raise ValueError("Nonfinite JSON value")

    return json.loads(read_bytes(path, max_bytes), parse_constant=reject)


def file_record(path, max_bytes):
    path = Path(path)
    if any(part.lower().startswith(".env") for part in path.parts):
        raise ValueError("Credential paths are not acceptance artifacts")
    digest, size = hashlib.sha256(), 0
    with open_regular(path.parent, path.name, max_bytes=max_bytes) as handle:
        while chunk := handle.read(min(1024 * 1024, max_bytes + 1 - size)):
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("Artifact exceeds its bounded read limit")
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name("." + path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def dispatch_summary(calls):
    """Separate confirmed zero-dispatch records from attempted/uncertain SDK calls."""
    cancelled = sum(
        row.get("outcome") == "not_dispatched"
        or row.get("charge_basis") == "confirmed_not_dispatched"
        for row in calls
    )
    uncertain = sum(
        row.get("outcome") != "not_dispatched"
        and row.get("charge_basis") != "confirmed_not_dispatched"
        and (row.get("outcome") == "pending" or row.get("settled") is not True)
        for row in calls
    )
    return {
        "recorded_calls": len(calls),
        "attempted_calls": len(calls) - cancelled - uncertain,
        "confirmed_not_dispatched": cancelled,
        "dispatch_unresolved": uncertain > 0,
    }


@dataclass
class AcceptanceRun:
    run_id: str
    provenance: str
    store: Store
    budget: BudgetLedger
    bundle: object
    profile: object
    artifact_dir: Path

    @property
    def router(self):
        return self.bundle.router

    def snapshot(self):
        return {
            "run_id": self.run_id,
            "provenance": self.provenance,
            "calls": self.store.llm_calls(self.run_id),
            "usage": self.store.usage(self.run_id),
            "budget": self.budget.snapshot(self.run_id),
        }


@contextmanager
def acceptance_run(
    *,
    case_id,
    artifact_dir,
    profile_path,
    run_limit_usd,
    daily_limit_usd,
    execute=False,
    live_authorized=False,
    project_root=PROJECT_ROOT,
    transport=None,
    env_file=None,
):
    """One case, one normal runtime and the existing authoritative shared ledger.

    A driver may call its router once. SDK retry policy is unchanged; unknown
    billing blocks retries through the ordinary shared runtime hooks.
    """
    if execute is not True or live_authorized is not True:
        raise ValueError("Execution and task-specific live authorization must both be explicit")
    if not isinstance(case_id, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}", case_id):
        raise ValueError("Invalid acceptance case identifier")
    project_root = Path(project_root).resolve()
    if transport is not None and not isinstance(transport, httpx.MockTransport):
        raise ValueError("Only offline MockTransport injection is allowed")
    if transport is None and project_root != PROJECT_ROOT.resolve():
        raise ValueError("Live acceptance must use the project shared ledger and Store")
    if transport is not None and project_root == PROJECT_ROOT.resolve():
        raise ValueError("Offline fixtures must not write the production ledger")
    if (
        transport is None
        and env_file is not None
        and Path(env_file).resolve() != PROJECT_ROOT / ".env"
    ):
        raise ValueError("Live acceptance uses the existing private project credential file")
    requested_limit, requested_daily = money(run_limit_usd), money(daily_limit_usd)
    limit = min(requested_limit, money(os.environ.get("HEADROOM_RUN_BUDGET_USD", run_limit_usd)))
    daily = min(
        requested_daily, money(os.environ.get("HEADROOM_DAILY_BUDGET_USD", daily_limit_usd))
    )
    if limit <= 0 or daily <= 0:
        raise ValueError("Explicit positive run and daily admission limits are required")
    directory = Path(artifact_dir)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    run_id = uuid4().hex
    provenance = "offline_fixture" if transport is not None else "live"
    store = budget = bundle = session = None
    opened = False
    caught = None
    record = {
        "run_id": run_id,
        "case_id": case_id,
        "provenance": provenance,
        "status": "preflight",
        "accepted": False,
        "requested_admission_run_limit_usd": str(requested_limit),
        "requested_daily_limit_usd": str(requested_daily),
        "admission_run_limit_usd": str(limit),
        "daily_limit_usd": str(daily),
        "authorization_expanded": False,
        "calls": [],
        "usage": None,
        "budget": None,
    }
    write_json(directory / "runtime.json", record)
    try:
        profile_hash = file_record(profile_path, 256 * 1024)["sha256"]
        profile = read_live_profile(profile_path)
        if file_record(profile_path, 256 * 1024)["sha256"] != profile_hash:
            raise ValueError("Runtime profile changed during verification")
        record["profile_sha256"] = profile_hash
        record["run_budget_mode"] = profile.run_budget_mode
        budget = BudgetLedger(
            project_root / ".cache/budget.db",
            daily_limit=daily,
            total_limit=profile.authorized_total_usd,
        )
        store = Store(project_root / "runs/acceptance/headroom.db")
        store.create_run(
            run_id,
            {
                "status": "running",
                "target": "acceptance:" + case_id,
                "provenance": provenance,
                "run_dir": str(directory),
                "acceptance_case": case_id,
                "accepted": False,
            },
        )
        budget.open_run(run_id, limit, budget_mode=profile.run_budget_mode)
        opened = True
        bundle = build_live_runtime(
            run_id,
            profile=profile,
            budget=budget,
            store=store,
            env_file=Path(env_file) if env_file is not None else project_root / ".env",
            transport=transport,
        )
        session = AcceptanceRun(run_id, provenance, store, budget, bundle, profile, directory)
        record["status"] = "running"
        write_json(directory / "runtime.json", record)
        yield session
        record["status"] = "completed"
    except BaseException as error:
        caught = error
        record.update(status="blocked_or_failed", error_type=type(error).__name__)
        raise
    finally:
        failures = []
        cleanup_interrupt = None
        if bundle is not None:
            try:
                bundle.close()
            except BaseException as error:  # noqa: BLE001 - finish accounting, then preserve interruption
                failures.append(type(error).__name__)
                if not isinstance(error, Exception):
                    cleanup_interrupt = cleanup_interrupt or error
        if opened:
            try:
                budget.close_run(run_id)
            except BaseException as error:  # noqa: BLE001 - finish accounting, then preserve interruption
                failures.append(type(error).__name__)
                if not isinstance(error, Exception):
                    cleanup_interrupt = cleanup_interrupt or error
        if store is not None:
            try:
                record["calls"] = store.llm_calls(run_id)
                record["usage"] = store.usage(run_id)
                if opened:
                    record["budget"] = budget.snapshot(run_id)
                store.update_run(run_id, status=record["status"], accepted=False)
            except BaseException as error:  # noqa: BLE001 - finish accounting, then preserve interruption
                failures.append(type(error).__name__)
                if not isinstance(error, Exception):
                    cleanup_interrupt = cleanup_interrupt or error
        record["cleanup_errors"] = failures
        try:
            write_json(directory / "runtime.json", record)
        except BaseException as error:  # noqa: BLE001 - close Store before preserving interruption
            failures.append(type(error).__name__)
            if not isinstance(error, Exception):
                cleanup_interrupt = cleanup_interrupt or error
        finally:
            if store is not None:
                try:
                    store.close()
                except BaseException as error:  # noqa: BLE001 - preserved below
                    failures.append(type(error).__name__)
                    if not isinstance(error, Exception):
                        cleanup_interrupt = cleanup_interrupt or error
        if caught is None and cleanup_interrupt is not None:
            raise cleanup_interrupt
        if caught is None and failures:
            raise RuntimeError("Acceptance runtime finalization failed; inspect retained evidence")
