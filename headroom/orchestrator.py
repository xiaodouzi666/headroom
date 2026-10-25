"""Baseline/evidence/diagnosis/patch/verification pipeline with durable partial results."""

import json
import os
import re
import shutil
import signal
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from headroom.annotate import annotate_stacks
from headroom.budget import BudgetExceeded, BudgetLedger, RunBudgetReached, money
from headroom.diagnose import diagnose_with_router, round_verification_feedback
from headroom.evidence import annotate_evidence_bundle, build_evidence
from headroom.execution import prepare_local_command, replay_argv
from headroom.lab.runner import PROJECT_ROOT, run_script
from headroom.llm.client import LLMError
from headroom.patch import PatchEngine
from headroom.report import generate_report
from headroom.research.tavily_tool import ResearchSession
from headroom.research.tool_loop import ResearchToolLoop
from headroom.runtime import RuntimeNotReady, build_live_runtime, read_live_profile
from headroom.search import (
    baseline_target_met,
    decide_keep,
    pareto_point,
    peak_gb,
    select_research_topics,
    write_cumulative_patch,
    write_pareto,
)
from headroom.solver_context import candidate_context, candidate_evidence, execution_context
from headroom.store.db import Store, _bounded_cost
from headroom.verify.compare import parse_target
from headroom.verify.policy import nanogpt_cli, scan_source_forbidden
from headroom.verify.runner import verify_script


class RunCancelled(BaseException):
    """The owned job process was asked to stop at its global deadline."""


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    allow_numerics_change: bool = False
    allow_model_change: bool = False
    allow_batch_grad_accum: bool = True
    max_throughput_regression_pct: float = Field(default=25, ge=0, le=1000)


class FixRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    script: str
    source_root: str | None = None
    script_args: list[str] = Field(default_factory=list, max_length=100)
    execution_argv: list[str] | None = Field(default=None, max_length=256)
    execution_entrypoint: dict | None = None
    repository_mode: bool = False
    target: str = "fix-oom"
    reclaim_reduction_pct: float = Field(default=30.0, gt=0, le=100)
    policy: Policy = Field(default_factory=Policy)
    max_steps: int = Field(default=20, ge=1, le=10000)
    max_seconds: int = Field(default=120, ge=1, le=3600)
    seed: int = Field(default=1337, ge=0, lt=2**32)
    device: str = "cuda"
    budget_usd: str = "0.6"
    daily_budget_usd: str = "12"
    allocator_conf: str | None = None
    runtime_profile: str | None = None
    max_rounds: int = Field(default=6, ge=1, le=6)
    search_mode: Literal["until_target", "bounded_pareto"] = "until_target"
    source_profile: str | None = None
    research_enabled: bool = True


@dataclass
class Services:
    baseline: Callable = run_script
    evidence: Callable = build_evidence
    verify: Callable = verify_script
    patch_factory: Callable = PatchEngine
    diagnose: Callable = diagnose_with_router
    evaluation_condition: str | None = None
    runtime_factory: Callable | None = None
    research_factory: Callable | None = None
    provenance: str = "live"
    evidence_token_budget: int = 150000


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temp.replace(path)


def _artifact(directory, value):
    if not value:
        return None
    path = Path(value).resolve()
    return (
        str(path.relative_to(directory.resolve()))
        if path.is_relative_to(directory.resolve())
        else None
    )


def _required_reduction(result, target, *, original_baseline=None, reclaim_reduction_pct=30):
    kind, limit = parse_target(target)
    # OOM peaks are lower bounds, not the memory needed to finish a workload.
    measured = peak_gb(result)
    if result.get("status") != "completed" or measured is None:
        return None
    peak = Decimal(str(measured))
    if kind == "fit":
        return float(max(Decimal(0), peak - limit / Decimal(10**9)))
    if kind == "reclaim":
        original = result if original_baseline is None else original_baseline
        original_peak = peak_gb(original)
        if original.get("status") != "completed" or original_peak is None:
            return None
        # Match the requested reclaim target against the fixed original baseline.
        limit_gb = Decimal(str(original_peak)) * (1 - Decimal(str(reclaim_reduction_pct)) / 100)
        return float(max(Decimal(0), peak - limit_gb))
    return None


def _llm_phase(store, run_id, start):
    records = store.llm_calls(run_id)[start:]
    details = []
    for row in records:
        cost = row.get("cost_usd")
        upper = _bounded_cost(row) if cost is None else None
        elapsed = row.get("elapsed_seconds")
        elapsed = elapsed if type(elapsed) in (int, float) and elapsed >= 0 else None
        details.append(
            {
                "model": row.get("model"),
                "role": row.get("role"),
                "elapsed_seconds": elapsed,
                "cost_usd": cost,
                "cost_upper_usd": str(upper) if upper is not None else None,
                "cost_basis": "actual"
                if cost is not None
                else "verified_upper_bound"
                if upper is not None
                else None,
                "outcome": row.get("outcome"),
                "billing_status": row.get("billing_status"),
            }
        )
    models = list(
        dict.fromkeys(row["model"] for row in details if row["model"] and row["model"] != "unknown")
    )
    known_cost = bool(details) and all(row["cost_usd"] is not None for row in details)
    known_time = bool(details) and all(row["elapsed_seconds"] is not None for row in details)
    covered = bool(details) and all(
        (row["cost_usd"] is not None or row["cost_upper_usd"] is not None)
        and row["billing_status"] not in {"unresolved", "pending"}
        for row in details
    )
    with localcontext() as context:
        context.prec = 256
        conservative = (
            sum(
                (
                    money(row["cost_usd"] if row["cost_usd"] is not None else row["cost_upper_usd"])
                    for row in details
                ),
                Decimal(0),
            )
            if covered
            else None
        )
    return {
        "models": models,
        "model": models[0] if len(models) == 1 else None,
        "cost_usd": str(sum((money(row["cost_usd"]) for row in details), Decimal(0)))
        if known_cost
        else None,
        "cost_upper_usd": str(conservative) if covered and not known_cost else None,
        "cost_basis": "actual" if known_cost else "verified_upper_bound" if covered else None,
        "billing_complete": covered,
        "elapsed_seconds": sum(row["elapsed_seconds"] for row in details) if known_time else None,
        "llm_calls": details,
    }


def _optional_annotations(router, evidence, provenance):
    if provenance != "live":
        return {
            "status": "skipped",
            "reason": "offline_fixture",
            "annotations": [],
            "acceptance": False,
            "note": "Offline orchestration does not call Nano.",
        }
    return annotate_stacks(router, evidence)


def _research_patch_context(result):
    context = result.get("context", "")
    encoded = context.encode("utf-8")
    limited = encoded[:24000].decode("utf-8", errors="ignore")
    if len(encoded) > 24000:
        limited += "\n[Research excerpt truncated to 24,000 UTF-8 bytes; full cached evidence remains recorded.]"
    return {key: result.get(key) for key in ("status", "topic", "sources", "notes")} | {
        "context": limited
    }


def _research_session(run_id, baseline, services, store, *, enabled):
    if not enabled:
        return None, "disabled"
    version = baseline.get("env", {}).get("torch")
    if not isinstance(version, str) or not re.fullmatch(
        r"[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[+.-][A-Za-z0-9_.+-]+)?", version
    ):
        return None, "torch_version_unavailable"
    live = services.provenance == "live" and services.runtime_factory is None
    key = None
    if live:
        # Executed only after the reviewed Nebius runtime exists. Tests inject a
        # runtime/research factory and must never read the actual private file.
        import stat

        from dotenv import dotenv_values

        private = PROJECT_ROOT / ".env"
        if (
            private.is_file()
            and not private.is_symlink()
            and stat.S_IMODE(private.stat().st_mode) == 0o600
        ):
            key = (dotenv_values(private, interpolate=False).get("TAVILY_API_KEY") or "").strip()
    factory = services.research_factory or ResearchSession.for_run
    return factory(
        run_id,
        torch_version=version,
        store=store,
        cache_dir=PROJECT_ROOT / ".cache/tavily",
        api_key=key,
        live=live,
        max_calls=4,
    ), None


def run_fix(
    request: FixRequest, *, store=None, run_root=None, services=None, run_id=None, on_event=None
):
    services = services or Services()
    parse_target(request.target)
    if request.device not in {"cpu", "cuda"}:
        raise ValueError("Device must be cpu or cuda")
    source_script = Path(request.script).resolve(strict=True)
    source = (
        Path(request.source_root).resolve(strict=True)
        if request.source_root
        else source_script.parent
    )
    if (
        not source_script.is_file()
        or source_script.suffix.lower() != ".py"
        or not source_script.is_relative_to(source)
    ):
        raise ValueError("Script must be a Python file inside its source root")
    if request.execution_argv is not None:
        prepared = prepare_local_command(
            source, request.execution_argv, execution_entrypoint=request.execution_entrypoint
        )
        if (
            prepared.script.resolve() != source_script
            or list(prepared.script_args) != request.script_args
        ):
            raise ValueError(
                "Execution argv must match the requested source and original script_args"
            )
    if request.repository_mode and request.execution_argv is None:
        raise ValueError("Repository command mode requires execution_argv")
    if request.execution_entrypoint is not None and request.execution_argv is None:
        raise ValueError("Captured entrypoint requires its original command argv")
    execution_options = (
        {"execution_argv": request.execution_argv} if request.execution_argv is not None else {}
    )
    if request.execution_entrypoint is not None:
        execution_options["execution_entrypoint"] = request.execution_entrypoint
    relative = source_script.relative_to(source)
    limit = min(
        money(request.budget_usd),
        money(os.environ.get("HEADROOM_RUN_BUDGET_USD", request.budget_usd)),
    )
    daily = min(
        money(request.daily_budget_usd),
        money(os.environ.get("HEADROOM_DAILY_BUDGET_USD", request.daily_budget_usd)),
    )
    if limit <= 0 or daily <= 0:
        raise ValueError("Budgets must be positive")
    root = Path(run_root or PROJECT_ROOT / "runs/jobs").resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_id = run_id or uuid.uuid4().hex
    if not re.fullmatch("[a-f0-9]{32}", run_id):
        raise ValueError("Run ID must be a generated UUID hex value")
    directory = root / run_id
    directory.mkdir(mode=0o700, exist_ok=False)
    owned_store = store is None
    store = store or Store(PROJECT_ROOT / "runs/headroom.db")
    data = {
        "status": "running",
        "target": request.target,
        "policy": request.policy.model_dump(),
        "request": request.model_dump(),
        "run_dir": str(directory),
        "provenance": services.provenance,
        "evaluation_condition": services.evaluation_condition,
        "target_met": False,
        "baseline": None,
        "after": None,
        "kept": None,
        "pareto": {"points": [], "frontier": []},
        "research": {"status": "not_started"},
        "search": {
            "mode": request.search_mode,
            "baseline_target_met": None,
            "first_target_met_round": None,
            "stop_reason": None,
            "rounds_executed": 0,
        },
    }
    if store.get_run(run_id) is None:
        store.create_run(run_id, data)
    else:
        store.update_run(run_id, data)

    def emit(kind, **payload):
        event = store.add_event(run_id, kind, payload)
        if on_event:
            on_event(event)
        return event

    started = time.monotonic()
    bundle = budget = research_session = research_loop = None
    budget_open = False
    evidence, artifacts = {}, {}
    sources, points, history = [], [], []
    verification_feedback = []
    candidate_history = []
    diagnosis = verification = None
    status, reason = "failed", None
    active_round = None
    research_results = {}
    research_ready = False
    research_reason = None
    emit("run.started", target=request.target, provenance=services.provenance)

    def finish_round(payload):
        nonlocal active_round
        row = {**(active_round or {}), **payload}
        feedback = round_verification_feedback(
            row,
            selected_result=data.get("after") or data.get("baseline"),
            selected_round=data["kept"]["round"] if data.get("kept") else None,
            selected_target_met=data["target_met"]
            if data.get("kept")
            else data["search"]["baseline_target_met"],
        )
        recorded_candidate = candidate_evidence(
            directory, row, selected_round=data["kept"]["round"] if data.get("kept") else None
        )
        candidate_history.append(recorded_candidate)
        row["candidate_evidence"] = recorded_candidate
        feedback_path = directory / "rounds" / f"{row['number']:02d}" / "verification-feedback.json"
        _write(feedback_path, feedback)
        row["verification_feedback"] = feedback
        row["verification_feedback_artifact"] = _artifact(directory, feedback_path)
        verification_feedback.append(feedback)
        store.add_round(run_id, row)
        history.append(
            {
                key: row.get(key)
                for key in (
                    "number",
                    "fix_id",
                    "decision",
                    "reason",
                    "memory_improvement_pct",
                    "current_throughput_regression_pct",
                )
            }
        )
        active_round = None
        data["search"]["rounds_executed"] = len(history)
        store.update_run(run_id, search=data["search"])
        emit("round.done", decision=row["decision"], round=row["number"], reason=row["reason"])

    previous_sigterm = None
    if threading.current_thread() is threading.main_thread():
        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def stop_job(signum, frame):
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            raise RunCancelled("Job wall-clock deadline reached")

        signal.signal(signal.SIGTERM, stop_job)
    try:
        emit("run.preflight", stage="runtime_and_budget")
        # Live custom execution cannot claim the pinned-code sandbox exception.
        sandboxed = services.baseline is run_script or services.provenance == "offline_fixture"
        if request.source_profile and not sandboxed:
            raise RuntimeNotReady("Pinned source profile requires the verified Docker Lab")
        source_kwargs = {"source_profile": request.source_profile, "sandboxed": sandboxed}
        if request.source_profile == "pinned_nanogpt":
            nanogpt_cli(request.script_args)
        source_policy = scan_source_forbidden(source, source_files=[str(relative)], **source_kwargs)
        if not source_policy.allowed:
            raise RuntimeNotReady(
                "Source safety checks rejected the input; no model request was sent"
            )
        if services.runtime_factory is None:
            profile = (
                read_live_profile(request.runtime_profile)
                if request.runtime_profile
                else read_live_profile()
            )
            budget = BudgetLedger(
                PROJECT_ROOT / ".cache/budget.db",
                daily_limit=daily,
                total_limit=profile.authorized_total_usd,
            )
            budget.open_run(run_id, limit, budget_mode=profile.run_budget_mode)
            budget_open = True
            bundle = build_live_runtime(run_id, profile=profile, budget=budget, store=store)
        else:
            bundle = services.runtime_factory(run_id, store, directory)
        emit(
            "budget.reserved",
            limit_usd=str(limit),
            live=services.provenance == "live",
            run_budget_mode=profile.run_budget_mode if budget_open else None,
        )
        emit("baseline.started", script=str(relative), device=request.device)
        baseline = services.baseline(
            source_script,
            source_root=source,
            script_args=request.script_args,
            run_root=directory / "lab",
            max_steps=request.max_steps,
            max_seconds=request.max_seconds,
            seed=request.seed,
            device=request.device,
            allocator_conf=request.allocator_conf,
            **execution_options,
        )
        data["baseline"] = baseline
        data["search"]["baseline_target_met"] = baseline_target_met(
            baseline, request.target, required_steps=request.max_steps
        )
        store.update_run(run_id, baseline=baseline, search=data["search"])
        if baseline.get("status") not in {"completed", "oom"}:
            raise RuntimeNotReady(
                "Baseline did not complete or produce a valid CUDA OOM: "
                + str(baseline.get("reason", "unknown"))
            )
        emit(
            "baseline.oom" if baseline["status"] == "oom" else "baseline.completed",
            lab_run_id=baseline.get("run_id"),
            peak_alloc_gb=baseline.get("peak_alloc_gb"),
        )
        original_source = Path(baseline["run_dir"]) / "source"
        emit("evidence.started", lab_run_id=baseline.get("run_id"))
        current_evidence = services.evidence(
            Path(baseline["run_dir"]),
            budget=bundle.evidence_token_budget,
            output_dir=directory / "evidence/before",
        )
        evidence["before"] = current_evidence
        artifacts["before_png"] = _artifact(directory, current_evidence.get("evidence_png"))
        emit("evidence.built", token_count=current_evidence.get("token_count"), round=0)
        initial_evidence_json = json.loads(Path(current_evidence["evidence_json"]).read_text())
        initial_files = [
            entry["path"] for entry in initial_evidence_json.get("sources", []) if "path" in entry
        ] or [str(relative)]
        if not scan_source_forbidden(
            original_source, source_files=initial_files, **source_kwargs
        ).allowed:
            raise RuntimeNotReady("Captured source safety checks rejected model context")
        annotate_start = len(store.llm_calls(run_id))
        data["annotations"] = _optional_annotations(
            bundle.router, initial_evidence_json, services.provenance
        )
        current_evidence = annotate_evidence_bundle(
            current_evidence, data["annotations"], provenance=services.provenance
        )
        evidence["before"] = current_evidence
        _write(directory / "annotations.json", data["annotations"])
        store.update_run(run_id, annotations=data["annotations"])
        artifacts["annotations"] = "annotations.json"
        if services.provenance == "live":
            emit(
                "annotate.done",
                status=data["annotations"]["status"],
                **_llm_phase(store, run_id, annotate_start),
            )
        current_source, current_result = original_source, baseline
        current_args, current_allocator = tuple(request.script_args), request.allocator_conf
        current_numerics = "none"
        original_reference = None
        policy = request.policy.model_dump()

        for number in range(1, request.max_rounds + 1):
            active_round = {
                "number": number,
                "decision": "revert",
                "reason": "interrupted",
                "current_source": _artifact(directory, current_source),
                "provenance": services.provenance,
            }
            round_dir = directory / "rounds" / f"{number:02d}"
            round_dir.mkdir(parents=True)
            evidence_json = json.loads(Path(current_evidence["evidence_json"]).read_text())
            source_files = [
                entry["path"] for entry in evidence_json.get("sources", []) if "path" in entry
            ]
            source_files = source_files or [str(relative)]
            # Inspect exactly the source actually captured/referenced by this evidence.
            actual_capture = Path(current_result["run_dir"]) / "source"
            for inspected in {current_source, actual_capture}:
                if not scan_source_forbidden(
                    inspected, source_files=source_files, **source_kwargs
                ).allowed:
                    raise RuntimeNotReady("Captured source safety checks rejected model context")
            invocation = execution_context(
                script=str(relative),
                script_args=current_args,
                execution_argv=(
                    replay_argv(
                        request.execution_argv,
                        current_args,
                        execution_entrypoint=request.execution_entrypoint,
                    )
                    if request.execution_argv is not None
                    else None
                ),
                source_files=evidence_json.get("sources", []),
                selected_round=data["kept"]["round"] if data.get("kept") else None,
                repository_mode=request.repository_mode,
                seed=request.seed,
                max_steps=request.max_steps,
                device=request.device,
                allocator_conf=current_allocator,
            )
            prior_candidates = candidate_context(candidate_history)
            prompt_evidence = Path(current_evidence["evidence_md"]).read_text()
            prompt_evidence += "\n\nSEARCH STATE (trusted orchestration metadata):\n" + json.dumps(
                {
                    "round": number,
                    "search_mode": request.search_mode,
                    "rounds_remaining": request.max_rounds - number + 1,
                    "target_already_met": data["target_met"],
                    "previous_rounds": history,
                    "current_kept": data["kept"],
                    "original_numerics_and_parameter_baseline_is_fixed": True,
                },
                allow_nan=False,
            )
            diagnose_start = len(store.llm_calls(run_id))
            emit("diagnose.started", role="diagnose", round=number)
            diagnostic_evidence = {
                **evidence_json,
                "execution_context": invocation,
                "candidate_evidence": prior_candidates,
                "search_state": {
                    "round": number,
                    "mode": request.search_mode,
                    "target_already_met": data["target_met"],
                    "previous_rounds": [
                        {key: row.get(key) for key in ("number", "fix_id", "decision", "reason")}
                        for row in history
                    ],
                    "current_kept": {
                        "round": data["kept"]["round"],
                        "numerics_impact": current_numerics,
                    }
                    if data["kept"]
                    else None,
                    "policy_flags": {
                        key: policy[key]
                        for key in (
                            "allow_numerics_change",
                            "allow_model_change",
                            "allow_batch_grad_accum",
                        )
                    },
                },
            }
            checked = services.diagnose(
                bundle.router,
                prompt_evidence,
                evidence=diagnostic_evidence,
                goal=request.target,
                policy=policy,
                verification_feedback=verification_feedback,
                required_saving_gb=_required_reduction(
                    current_result,
                    request.target,
                    original_baseline=baseline,
                    reclaim_reduction_pct=request.reclaim_reduction_pct,
                ),
            )
            diagnosis = checked.diagnosis.model_dump() if checked.diagnosis else None
            diagnosis_data = {
                "diagnosis": diagnosis,
                "issues": [asdict(i) for i in checked.issues],
                "valid": checked.valid,
                "ready_for_patch": checked.ready_for_patch,
                "requires_supplement": checked.requires_supplement,
                "supplement_request": checked.supplement_request,
            }
            _write(round_dir / "diagnosis.json", diagnosis_data)
            _write(directory / "diagnosis.json", diagnosis_data)
            emit(
                "diagnose.done",
                valid=checked.valid,
                ready_for_patch=checked.ready_for_patch,
                round=number,
                **_llm_phase(store, run_id, diagnose_start),
            )
            if not checked.ready_for_patch:
                needs_information = bool(
                    checked.diagnosis is not None and checked.diagnosis.needs_more_info
                )
                blocked_reason = (
                    "diagnosis_needs_more_info" if needs_information else "diagnosis_not_ready"
                )
                finish_round(
                    {
                        "reason": blocked_reason,
                        "diagnosis": _artifact(directory, round_dir / "diagnosis.json"),
                        "requested_information": (
                            checked.diagnosis.notes if needs_information else []
                        ),
                        "supplement_request": checked.supplement_request,
                    }
                )
                if needs_information:
                    data["search"]["stop_reason"] = "diagnosis_needs_more_info"
                    raise RuntimeNotReady(
                        "Diagnosis requests additional information; inspect diagnosis.json notes "
                        "before restarting with new evidence"
                    )
                if checked.requires_supplement:
                    data["search"]["stop_reason"] = "diagnosis_supplement_exhausted"
                    raise RuntimeNotReady(
                        "Diagnosis still lacks sufficient evidenced savings after the bounded "
                        "supplement; inspect diagnosis.json before restarting"
                    )
                continue
            step = checked.diagnosis.plan[0]
            step_data = step.model_dump()
            active_round["fix_id"] = step.fix_id
            active_round["plan_step"] = step_data
            # Topic hints identify the proposed API. Super chooses the actual tools.
            topics = select_research_topics(step_data)
            if not research_ready and (topics or not request.research_enabled):
                try:
                    research_session, research_reason = _research_session(
                        run_id, baseline, services, store, enabled=request.research_enabled
                    )
                except BudgetExceeded:
                    raise
                except (OSError, ValueError, TypeError, RuntimeError):
                    research_session, research_reason = None, "session_unavailable"
                research_ready = True
                if research_session is not None:
                    research_loop = ResearchToolLoop(bundle.router, research_session)
                if research_reason:
                    skipped = {
                        "provider": "tavily",
                        "status": "skipped",
                        "reason": research_reason,
                        "api_calls": 0,
                    }
                    store.add_research(run_id, skipped)
                    emit("research.done", status="skipped", reason=research_reason, api_calls=0)
                    data["research"] = skipped

            def save_research(
                result,
                round_dir=round_dir,
                research_session=research_session,
                research_loop=research_loop,
            ):
                topic = result["topic"]
                research_results[topic] = result
                for citation in result.get("sources", []):
                    if not any(existing["url"] == citation["url"] for existing in sources):
                        sources.append(citation)
                _write(round_dir / f"research-{topic}.json", result)
                results = list(research_results.values())
                operations = [op for item in results for op in item.get("operations", [])]
                succeeded = any(op.get("status") in {"succeeded", "cached"} for op in operations)
                data["research"] = {
                    "status": (
                        "completed"
                        if results and all(item["status"] == "succeeded" for item in results)
                        else "partial"
                        if succeeded
                        else "skipped"
                        if all(item["status"] == "not_executed" for item in results)
                        else "failed"
                    ),
                    "mechanism": "model_tool_calls",
                    "topics": list(research_results),
                    "api_calls": research_session.api_calls,
                    "model_turns": research_loop.model_turns,
                    "model_attempts": research_loop.model_attempts,
                    "tool_calls": research_loop.tool_calls,
                    "stop_reason": result.get("stop_reason"),
                    "sources": sources,
                    "operations": operations,
                }
                store.update_run(run_id, research=data["research"])

            for topic in topics:
                if topic in research_results or research_loop is None:
                    continue
                research_start = len(store.llm_calls(run_id))
                try:
                    research_loop.research(topic, step_data, on_update=save_research)
                finally:
                    # Includes rejected/unknown attempts; model cost is never Tavily credits.
                    emit(
                        "research.done",
                        topic=topic,
                        round=number,
                        status=data["research"].get("status"),
                        reason=data["research"].get("stop_reason"),
                        api_calls=data["research"].get("api_calls", 0),
                        **_llm_phase(store, run_id, research_start),
                    )
            if (
                not research_results
                and research_session is not None
                or not topics
                and not research_ready
            ):
                data["research"] = {
                    "status": "skipped",
                    "reason": "no_applicable_api_topic",
                    "api_calls": 0,
                }
            store.update_run(run_id, research=data["research"])
            context = {
                "diagnosis": diagnosis,
                "execution_context": invocation,
                "candidate_evidence": prior_candidates,
                "verification_feedback": verification_feedback,
                "goal": request.target,
                "search_mode": request.search_mode,
                "target_already_met": data["target_met"],
                "previous_rounds": history,
                "research": [
                    _research_patch_context(research_results[topic])
                    for topic in topics
                    if topic in research_results
                ],
            }
            patch_start = len(store.llm_calls(run_id))
            emit("patch.started", fix_id=step.fix_id, role="patcher", round=number)
            patch = services.patch_factory(bundle.router).generate_and_apply(
                current_source,
                step,
                work_root=round_dir / "patches",
                policy=policy,
                source_files=source_files,
                base_cli=current_args,
                context=context,
                **source_kwargs,
            )
            _write(round_dir / "patch-result.json", asdict(patch))
            _write(directory / "patch-result.json", asdict(patch))
            active_round.update(
                patch=_artifact(directory, patch.patch_path),
                candidate_dir=_artifact(directory, patch.candidate_dir),
            )
            emit(
                "patch.written",
                attempts=len(patch.attempts),
                status=patch.status,
                round=number,
                **_llm_phase(store, run_id, patch_start),
            )
            if not patch.applied:
                emit("patch.failed", reason=patch.reason, round=number)
                finish_round({"reason": patch.reason})
                continue
            emit("patch.applied", fix_id=step.fix_id, round=number)
            allocator = patch.env_changes.get("PYTORCH_CUDA_ALLOC_CONF", current_allocator)
            severity = {"none": 0, "minor": 1, "significant": 2}
            candidate_numerics = max((current_numerics, step.numerics_impact), key=severity.get)
            emit("verify.started", fix_id=step.fix_id, round=number)
            verified = services.verify(
                baseline,
                Path(patch.candidate_dir) / relative,
                baseline_script=original_source / relative,
                script_args=patch.effective_cli,
                baseline_args=request.script_args,
                candidate_source_root=patch.candidate_dir,
                baseline_source_root=original_source,
                run_root=directory / "lab",
                target=request.target,
                policy=policy,
                device=request.device,
                seed=request.seed,
                max_seconds=request.max_seconds,
                required_steps=request.max_steps,
                allocator_conf=allocator,
                baseline_allocator_conf=request.allocator_conf,
                numerics_impact=candidate_numerics,
                reference=original_reference,
                **execution_options,
                reclaim_reduction_pct=request.reclaim_reduction_pct,
                **({"acceptance_scope": "repository"} if request.repository_mode else {}),
            )
            if original_reference is None and verified.get("reference") is not None:
                original_reference = verified["reference"]
            report = verified["report"]
            candidate_verification = (
                report.model_dump() if hasattr(report, "model_dump") else dict(report)
            )
            candidate_verification["after"] = verified["candidate"]
            candidate_verification["reference_discovery"] = verified.get("reference_discovery")
            candidate_verification["pairing_evidence"] = verified.get("pairing_evidence")
            active_round["verification"] = candidate_verification
            _write(round_dir / "verification.json", candidate_verification)
            emit(
                "verify.done",
                target_met=candidate_verification["target_met"],
                loss_equivalence=candidate_verification["loss_equivalence"],
                round=number,
            )
            after_evidence = None
            if verified["candidate"].get("status") in {"completed", "oom"}:
                try:
                    after_evidence = services.evidence(
                        Path(verified["candidate"]["run_dir"]),
                        budget=bundle.evidence_token_budget,
                        output_dir=round_dir / "evidence",
                    )
                    if not isinstance(after_evidence, dict) or not all(
                        isinstance(after_evidence.get(key), str)
                        and Path(after_evidence[key]).is_file()
                        for key in ("evidence_json", "evidence_md")
                    ):
                        raise ValueError("Fresh evidence files unavailable")
                    active_round["evidence"] = _artifact(
                        directory, after_evidence.get("evidence_json")
                    )
                except (ValueError, OSError, TypeError) as error:
                    after_evidence = None
                    active_round["evidence_status"] = "unavailable"
                    candidate_verification.setdefault("notes", []).append(
                        "After evidence unavailable: " + type(error).__name__
                    )
            decision = decide_keep(
                current_result,
                verified["candidate"],
                candidate_verification,
                original_baseline=baseline,
                policy=policy,
                preserve_target=request.search_mode == "bounded_pareto" and data["target_met"],
            )
            active_round.update(asdict(decision))
            if decision.keep:
                cumulative_env = (
                    {"PYTORCH_CUDA_ALLOC_CONF": allocator}
                    if allocator != request.allocator_conf and allocator is not None
                    else {}
                )
                tier = write_cumulative_patch(
                    original_source,
                    patch.candidate_dir,
                    directory / "configurations" / f"round-{number:02d}",
                    env_changes=cumulative_env,
                    effective_cli=patch.effective_cli,
                    base_cli=request.script_args,
                    metadata={
                        "round": number,
                        "policy": policy,
                        "provenance": services.provenance,
                        "numerics_impact": candidate_numerics,
                        "original_source": str(original_source),
                        "original_execution_argv": request.execution_argv,
                        "execution_entrypoint": request.execution_entrypoint,
                        "execution_argv": replay_argv(
                            request.execution_argv,
                            patch.effective_cli,
                            execution_entrypoint=request.execution_entrypoint,
                        )
                        if request.execution_argv is not None
                        else None,
                    },
                )
                tier = {key: _artifact(directory, value) for key, value in tier.items()}
                point = pareto_point(
                    number,
                    verified["candidate"],
                    candidate_verification,
                    policy=policy,
                    artifacts=tier,
                    provenance=services.provenance,
                )
                points.append(point)
                next_pareto = write_pareto(directory, points)
                next_kept = {
                    "round": number,
                    "source": str(patch.candidate_dir),
                    "effective_cli": list(patch.effective_cli),
                    "execution_entrypoint": request.execution_entrypoint,
                    "execution_argv": replay_argv(
                        request.execution_argv,
                        patch.effective_cli,
                        execution_entrypoint=request.execution_entrypoint,
                    )
                    if request.execution_argv is not None
                    else None,
                    "allocator_conf": allocator,
                    "numerics_impact": candidate_numerics,
                    "artifacts": tier,
                }
                data.update(
                    pareto=next_pareto,
                    after=verified["candidate"],
                    kept=next_kept,
                    target_met=candidate_verification["target_met"] is True,
                )
                if data["target_met"] and data["search"]["first_target_met_round"] is None:
                    data["search"]["first_target_met_round"] = number
                verification = candidate_verification
                current_source, current_result = Path(patch.candidate_dir), verified["candidate"]
                current_args, current_allocator, current_numerics = (
                    tuple(patch.effective_cli),
                    allocator,
                    candidate_numerics,
                )
                # Evidence belongs to the selected configuration as a whole.
                evidence.pop("after", None)
                artifacts.pop("after_png", None)
                data["after_evidence_status"] = (
                    "available" if after_evidence is not None else "unavailable"
                )
                if after_evidence is not None:
                    evidence["after"] = after_evidence
                    current_evidence = after_evidence
                    artifacts["after_png"] = _artifact(
                        directory, after_evidence.get("evidence_png")
                    )
                shutil.copyfile(directory / tier["patch"], directory / "patch.diff")
                shutil.copyfile(directory / tier["env"], directory / "env.sh")
                shutil.copyfile(directory / tier["cli"], directory / "cli.json")
                artifacts.update(
                    patch=tier["patch"],
                    env=tier["env"],
                    cli=tier["cli"],
                    pareto_json="pareto.json",
                    pareto_md="pareto.md",
                )
                active_round["configuration"] = tier
                store.update_run(
                    run_id,
                    after=data["after"],
                    kept=data["kept"],
                    pareto=data["pareto"],
                    target_met=data["target_met"],
                    after_evidence_status=data["after_evidence_status"],
                    search=data["search"],
                )
            finish_round(
                {"decision": "keep" if decision.keep else "revert", "reason": decision.reason}
            )
            if decision.keep and data["target_met"]:
                if data["search"]["first_target_met_round"] == number:
                    emit("target.met", target=request.target, round=number)
                if request.search_mode == "until_target":
                    data["search"]["stop_reason"] = "target_met"
                    break
            if (
                decision.keep
                and after_evidence is None
                and (request.search_mode == "until_target" or number < request.max_rounds)
            ):
                data["search"]["stop_reason"] = "fresh_evidence_unavailable"
                raise RuntimeNotReady(
                    "Kept configuration is saved, but fresh evidence is unavailable for the next round"
                )
        status = "completed"
        if data["search"]["stop_reason"] is None:
            data["search"]["stop_reason"] = "max_rounds_reached"
        reason = None if data["search"]["stop_reason"] == "target_met" else "max_rounds_reached"
    except RunCancelled:
        status, reason = "timeout", "Job wall-clock deadline reached"
        data["search"]["stop_reason"] = "deadline"
        emit("run.failed", reason=reason)
    except BudgetExceeded as error:
        status, reason = "budget_exceeded", str(error)
        if isinstance(error, RunBudgetReached) and error.exceeded:
            # Preserve retained candidate/verification facts, but this run did not
            # certify its cost constraint (actual or conservative bound).
            data["target_met"] = False
        data["search"]["stop_reason"] = "budget_exceeded"
        emit("budget.exceeded", reason=reason)
    except RuntimeNotReady as error:
        status, reason = "needs_human", str(error)
        data["search"]["stop_reason"] = data["search"]["stop_reason"] or "runtime_not_ready"
        emit("needs_human", reason=reason)
    except (LLMError, OSError, ValueError, TypeError) as error:
        status, reason = "failed", "Pipeline failed: " + type(error).__name__
        data["search"]["stop_reason"] = "pipeline_error"
        emit("run.failed", reason=reason)
    finally:
        if active_round is not None:
            committed = (
                data.get("kept") is not None and data["kept"]["round"] == active_round["number"]
            )
            finish_round(
                {
                    "decision": "keep" if committed else "revert",
                    "reason": "memory_improved_within_constraints" if committed else status,
                    "failure": reason,
                }
            )
        if research_session is not None:
            try:
                research_session.close()
            except (OSError, ValueError, TypeError, RuntimeError) as error:
                data.setdefault("cleanup_errors", []).append("research:" + type(error).__name__)
        if bundle is not None:
            try:
                bundle.close()
            except (OSError, ValueError, TypeError, RuntimeError) as error:
                data.setdefault("cleanup_errors", []).append("runtime:" + type(error).__name__)
        if budget_open:
            data["budget"] = budget.close_run(run_id)
            final_budget = data["budget"]
            if final_budget["run_budget_mode"] == "actual_usage" and (
                final_budget["run_budget_exceeded"]
                or final_budget["billing_bound_unresolved"]
                or final_budget.get("billing_complete") is not True
                or final_budget["pending_attempts"]
                or final_budget.get("conservative_total_usd") is None
                or money(final_budget["conservative_total_usd"]) > money(final_budget["limit_usd"])
            ):
                # A retained configuration may still meet its memory target, but
                # unresolved or failed run cost cannot certify overall success.
                data["target_met"] = False
                if status == "completed":
                    status, reason = (
                        "budget_exceeded",
                        "Run cost is unresolved or its upper bound cannot establish its limit",
                    )
                    data["search"]["stop_reason"] = "budget_exceeded"
                    emit("budget.exceeded", reason=reason)
        if data.get("kept"):
            data["pareto"] = write_pareto(directory, data["pareto"]["points"])
            for key, filename in (("patch", "patch.diff"), ("env", "env.sh"), ("cli", "cli.json")):
                kept_path = directory / data["kept"]["artifacts"][key]
                temporary = directory / (filename + ".tmp")
                shutil.copyfile(kept_path, temporary)
                temporary.replace(directory / filename)
                artifacts[key] = data["kept"]["artifacts"][key]
        before_bundle = evidence.get("before", {})
        before_paths = {}
        for name, key in (("evidence.json", "evidence_json"), ("evidence.md", "evidence_md")):
            value = before_bundle.get(key) if isinstance(before_bundle, dict) else None
            try:
                # Keep the selected lexical locator: API reads still reject linked
                # ancestors/leaves and never substitute a different canonical file.
                relative_path = (
                    Path(value).relative_to(directory).as_posix()
                    if isinstance(value, str)
                    else None
                )
            except ValueError:
                relative_path = None
            before_paths[name] = relative_path
        data["before_evidence_paths"] = before_paths
        data.update(status=status, reason=reason, elapsed_seconds=time.monotonic() - started)
        store.update_run(run_id, data)
        emit("report.started", partial=status != "completed")
        document = generate_report(
            directory,
            store.get_run(run_id),
            evidence=evidence,
            rounds=store.rounds(run_id),
            verification=verification,
            usage=store.usage(run_id),
            diagnosis=diagnosis,
            sources=sources,
            artifacts={key: value for key, value in artifacts.items() if value},
        )
        emit("report.written", report="report.md")
        if status == "completed":
            emit("run.done", target_met=data["target_met"])
        result = {
            "run_id": run_id,
            "status": status,
            "target_met": data["target_met"],
            "reason": reason,
            "budget": data.get("budget"),
            "run_dir": str(directory),
            "report_json": str(directory / "report.json"),
            "report_md": str(directory / "report.md"),
            "report": document,
            "kept": data["kept"],
            "pareto": data["pareto"],
            "search": data["search"],
        }
        if owned_store:
            store.close()
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
    return result
