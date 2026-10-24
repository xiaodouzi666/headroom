"""Per-case process supervision for explicitly live evaluation campaigns."""

import json
import multiprocessing
import time
from pathlib import Path

from headroom.api.queue import cleanup_owned_lab
from headroom.api.security import job_directory, open_regular
from headroom.report import generate_report, render_markdown
from headroom.store.db import Store

RUN_WALL_LIMIT_SECONDS = 480
WORKER_GRACE_SECONDS = 5
MAX_RESULT_BYTES = 64 * 1024 * 1024


def _write(path, value):
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(raw) > MAX_RESULT_BYTES:
        raise ValueError("Evaluation result exceeds its bounded artifact domain")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(raw + b"\n")
    temporary.replace(path)


def _read(path):
    try:
        with open_regular(path.parent, path.name, MAX_RESULT_BYTES) as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def _evaluation_entry(
    request, store_path, run_root, run_id, condition, audit_dir, result_path, deadline, preparation
):
    # Construct closures in the child instead of pickling live SDK/Services objects.
    from headroom.evaluation import Scenario, _prepare, _source_hash, condition_services
    from headroom.orchestrator import FixRequest, run_fix

    store = Store(store_path)
    try:
        if time.monotonic() >= deadline:
            return
        prepared = None
        if preparation is not None:
            case = Scenario.model_validate(preparation["case"])
            input_dir = Path(preparation["input_dir"])
            input_dir.mkdir()
            script, source, args, execution = _prepare(
                case, Path(preparation["project_root"]), input_dir
            )
            request = {
                **request,
                "script": str(script),
                "source_root": str(source),
                "script_args": args,
                "execution_argv": execution["execution_argv"],
                "repository_mode": execution["repository_mode"],
            }
            prepared = {"source_sha256": _source_hash(script), "execution": execution}
            _write(Path(result_path).with_name("preparation-" + run_id + ".json"), prepared)
        if time.monotonic() >= deadline:
            return
        result = run_fix(
            FixRequest.model_validate(request),
            store=store,
            run_root=Path(run_root),
            run_id=run_id,
            services=condition_services(condition, Path(audit_dir)),
        )
        _write(Path(result_path), result)
    except Exception as error:  # noqa: BLE001 - public failure state omits exception text
        store.update_run(
            run_id,
            status="failed",
            target_met=False,
            reason="evaluation_worker_" + type(error).__name__,
        )
        store.add_event(run_id, "run.failed", {"reason": "evaluation_worker_error"})
    finally:
        store.close()


def supervise_evaluation_run(
    request,
    *,
    store,
    run_root,
    run_id,
    condition,
    audit_dir,
    started,
    preparation=None,
    wall_limit_seconds=RUN_WALL_LIMIT_SECONDS,
    _entrypoint=_evaluation_entry,
    _grace_seconds=WORKER_GRACE_SECONDS,
):
    """Own one Headroom process; user programs still execute only in its Docker Lab.

    Preparation time is included through the caller's monotonic started value.
    The 480-second execution deadline is not extended for cleanup. Pending or
    unknown provider charges are never released or replaced with zero here.
    Private injection parameters support short offline spawn tests only.
    """
    if not 0 < wall_limit_seconds <= RUN_WALL_LIMIT_SECONDS or not 0 <= _grace_seconds <= 5:
        raise ValueError("Evaluation supervision cannot extend its reviewed deadlines")
    deadline = started + wall_limit_seconds
    run_root = Path(run_root)
    directory = job_directory(run_root, run_id)
    result_path = run_root.parent / ("worker-result-" + run_id + ".json")
    state = {
        "status": "queued",
        "target_met": False,
        "target": request.target,
        "request": request.model_dump(),
        "run_dir": str(directory),
        "provenance": "live",
        "evaluation_condition": condition,
    }
    if store.get_run(run_id) is None:
        store.create_run(run_id, state)
    process = None
    worker_result = None
    timed_out = time.monotonic() >= deadline
    try:
        if not timed_out:
            process = multiprocessing.get_context("spawn").Process(
                target=_entrypoint,
                args=(
                    request.model_dump(),
                    str(store.path),
                    str(run_root),
                    run_id,
                    condition,
                    str(audit_dir),
                    str(result_path),
                    deadline,
                    preparation,
                ),
                daemon=True,
            )
            process.start()
            store.update_run(run_id, evaluation_worker_pid=process.pid)
            while process.is_alive() and time.monotonic() < deadline:
                process.join(min(0.1, max(0, deadline - time.monotonic())))
            timed_out = time.monotonic() >= deadline
    finally:
        cleanup_started = time.monotonic()
        if process is not None and process.is_alive():
            process.terminate()
            process.join(_grace_seconds)
            if process.is_alive():
                process.kill()
                process.join(5)
        alive = process is not None and process.is_alive()
        cleaned = not alive and cleanup_owned_lab(run_root, run_id)
        cleanup_seconds = time.monotonic() - cleanup_started
    worker_result = _read(result_path)
    worker_exit = process.exitcode if process is not None else None
    total_seconds = time.monotonic() - started
    timed_out = timed_out or total_seconds > wall_limit_seconds
    status = reason = None
    if not cleaned:
        status, reason = "needs_human", "evaluation_cleanup_unverified"
    elif timed_out:
        status, reason = "timeout", "evaluation_wall_deadline_exceeded"
    elif worker_exit != 0 or worker_result is None:
        status, reason = "failed", "evaluation_worker_result_unavailable"

    timing = {
        "limit_seconds": wall_limit_seconds,
        "wall_seconds": total_seconds,
        "cleanup_seconds": cleanup_seconds,
        "within_wall_limit": total_seconds <= wall_limit_seconds and not timed_out,
        "deadline_exceeded": timed_out,
        "worker_exit_code": worker_exit,
        "cleanup_verified": cleaned,
    }
    store.update_run(run_id, evaluation_timing=timing)
    if status is not None:
        state = store.get_run(run_id)
        search = dict(state.get("search") or {})
        search["stop_reason"] = "deadline" if timed_out else reason
        store.update_run(run_id, status=status, reason=reason, target_met=False, search=search)
        store.add_event(
            run_id,
            "run.failed",
            {"reason": reason, "cleanup_verified": cleaned, "deadline_seconds": wall_limit_seconds},
        )
    state = store.get_run(run_id)
    document = _read(directory / "report.json")
    if document is None:
        directory.mkdir(parents=True, exist_ok=True)
        document = generate_report(
            directory,
            state,
            rounds=store.rounds(run_id),
            usage=store.usage(run_id),
        )
    if status is not None:
        document.setdefault("run", {}).update(status=status, reason=reason)
        document.setdefault("summary", {})["target_met"] = False
        document["search"] = state.get("search", {})
        document.setdefault("warnings", []).append(
            "Evaluation did not finish within its supervised execution/cleanup requirements; "
            "saved candidate measurements are retained, not overall acceptance."
        )
    document["evaluation_timing"] = timing
    _write(directory / "report.json", document)
    temporary = directory / "report.md.tmp"
    temporary.write_text(render_markdown(document))
    temporary.replace(directory / "report.md")

    result = dict(worker_result or {})
    result.update(
        run_id=run_id,
        status=state.get("status", "failed"),
        target_met=state.get("target_met", False),
        reason=state.get("reason"),
        run_dir=str(directory),
        report_json=str(directory / "report.json"),
        report_md=str(directory / "report.md"),
        report=document,
        kept=state.get("kept"),
        pareto=state.get("pareto"),
        search=state.get("search"),
        evaluation_timing=timing,
        evaluation_preparation=_read(result_path.with_name("preparation-" + run_id + ".json")),
    )
    return result
