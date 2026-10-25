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


def _repository_invocation(case, root, input_dir):
    """Read the original repo CLI intent without preparing or executing it twice."""
    import yaml

    from headroom.cli_execution import RepositoryInvocation
    from headroom.evaluation import _inside
    from headroom.execution import command_argv, prepare_local_command
    from headroom.repository import validate_repository

    if not case.repository_manifest:
        if case.source_profile:
            raise ValueError("Pinned source policy needs its original repository identity")
        return None
    manifest = _inside(root, case.repository_manifest)
    with open_regular(manifest.parent, manifest.name, 1024 * 1024) as handle:
        raw = handle.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Repository command manifest exceeds its bound")
    metadata = yaml.safe_load(raw)
    if not isinstance(metadata, dict):
        raise TypeError("Repository command manifest must be an object")
    if "repository" not in metadata and "ref" not in metadata:
        if case.source_profile:
            raise ValueError("Pinned source policy needs its original repository identity")
        return None
    repository = validate_repository(metadata.get("repository"), metadata.get("ref"))
    command = list(command_argv(metadata.get("command")))
    declared = prepare_local_command(_inside(root, case.source_root), command)
    if (
        declared.script != _inside(root, case.script)
        or list(declared.script_args) != case.script_args
    ):
        raise ValueError("Repository command differs from the frozen scenario")
    return RepositoryInvocation(
        repository=repository,
        ref=metadata["ref"],
        command=command,
        destination=str(input_dir / "repository"),
    )


def _evaluation_entry(
    request, store_path, run_root, run_id, condition, audit_dir, result_path, deadline, preparation
):
    # This process becomes the installed CLI, preserving its PID and outer deadline.
    from headroom.cli_execution import (
        PACKAGE_ROOT,
        Invocation,
        cli_arguments,
        console_script,
        digest,
        launch,
    )
    from headroom.evaluation import Scenario, _inside, _prepare
    from headroom.orchestrator import FixRequest

    queued_request = dict(request)
    store = Store(store_path)
    try:
        if time.monotonic() >= deadline:
            return
        repository = None
        source_hash = None
        if preparation is not None:
            case = Scenario.model_validate(preparation["case"])
            root = Path(preparation["project_root"])
            input_dir = Path(preparation["input_dir"])
            input_dir.mkdir()
            source_hash = digest(_inside(root, case.script))
            if case.source_sha256 is not None and source_hash != case.source_sha256:
                raise ValueError("Scenario source changed after manifest pin")
            if case.group == "repository":
                repository = _repository_invocation(case, root, input_dir)
            if repository is None:
                script, source, args, execution = _prepare(case, root, input_dir)
                request = {
                    **request,
                    "script": str(script),
                    "source_root": str(source),
                    "script_args": args,
                    "execution_argv": execution["execution_argv"],
                    "repository_mode": execution["repository_mode"],
                }
                _write(
                    Path(result_path).with_name("preparation-" + run_id + ".json"),
                    {"source_sha256": source_hash, "execution": execution},
                )
        if time.monotonic() >= deadline:
            return
        if request.get("source_root") is None:
            request = {**request, "source_root": str(Path(request["script"]).parent)}
        parsed = FixRequest.model_validate(request)
        console_path, console_hash = console_script()
        invocation = Invocation(
            run_id=run_id,
            request=parsed.model_dump(),
            queued_request=queued_request,
            store_path=str(store_path),
            run_root=str(run_root),
            audit_dir=str(audit_dir),
            result_path=str(result_path),
            deadline=float(deadline),
            condition=condition,
            study_protocol=(preparation or {}).get("study_protocol"),
            argv=cli_arguments(parsed, repository),
            package_root=str(PACKAGE_ROOT),
            console_path=console_path,
            console_sha256=console_hash,
            source_sha256=source_hash or digest(parsed.script),
            repository=repository,
        )
        store.close()
        store = None
        launch(invocation)
    except Exception as error:  # noqa: BLE001 - public failure state omits exception text
        if store is None:
            store = Store(store_path)
        store.update_run(
            run_id,
            status="failed",
            target_met=False,
            reason="evaluation_worker_" + type(error).__name__,
        )
        store.add_event(run_id, "run.failed", {"reason": "evaluation_worker_error"})
    finally:
        if store is not None:
            store.close()


def _verified_cli_receipt(path, worker_result, worker_exit, run_id, worker_pid):
    """Observe actual entrypoint/OS exits, never derive CLI success from workflow status."""
    import hashlib

    receipt = _read(path)
    if receipt is None:
        return None, False
    observed = receipt.get("observed_exit_code")
    valid = (
        receipt.get("invocation_kind") == "installed_console_script"
        and receipt.get("run_id") == run_id
        and receipt.get("pid") == worker_pid
        and receipt.get("invoked") is True
        and receipt.get("returned") is True
        and type(observed) is int
        and observed == worker_exit
        and receipt.get("run_dispatched") is True
        and receipt.get("result_saved") is True
        and isinstance(worker_result, dict)
        and worker_result.get("run_id") == run_id
    )
    if valid:
        result_path = path.with_name("worker-result-" + run_id + ".json")
        try:
            with open_regular(result_path.parent, result_path.name, MAX_RESULT_BYTES) as handle:
                raw = handle.read(MAX_RESULT_BYTES + 1)
            valid = len(raw) <= MAX_RESULT_BYTES and hashlib.sha256(raw).hexdigest() == receipt.get(
                "result_sha256"
            )
        except (OSError, ValueError):
            valid = False
    return receipt, valid


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
    from headroom.diagnosis_protocol import diagnosis_cap

    study_protocol = (preparation or {}).get("study_protocol")
    diagnosis_cap(study_protocol)
    if study_protocol is not None:
        state["study_protocol"] = study_protocol
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
    cli_receipt, cli_valid = _verified_cli_receipt(
        result_path.with_name("cli-invocation-" + run_id + ".json"),
        worker_result,
        worker_exit,
        run_id,
        process.pid if process else None,
    )
    total_seconds = time.monotonic() - started
    timed_out = timed_out or total_seconds > wall_limit_seconds
    status = reason = None
    if not cleaned:
        status, reason = "needs_human", "evaluation_cleanup_unverified"
    elif timed_out:
        status, reason = "timeout", "evaluation_wall_deadline_exceeded"
    elif (
        worker_result is None
        or (worker_exit != 0 and not cli_valid)
        or (_entrypoint is _evaluation_entry and not cli_valid)
    ):
        status, reason = "failed", "evaluation_worker_result_unavailable"

    timing = {
        "limit_seconds": wall_limit_seconds,
        "wall_seconds": total_seconds,
        "cleanup_seconds": cleanup_seconds,
        "within_wall_limit": total_seconds <= wall_limit_seconds and not timed_out,
        "deadline_exceeded": timed_out,
        "worker_exit_code": worker_exit,
        "cleanup_verified": cleaned,
        "cli": {
            **(cli_receipt or {"invoked": False, "observed_exit_code": None}),
            "verified": cli_valid,
        },
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
