"""Headroom command-line entry point."""

import json
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from headroom import __version__
from headroom.lab.envs import validate_allocator
from headroom.lab.runner import run_script
from headroom.verify.reference_config import NumericalReference


class ReferenceStrategyOption(str, Enum):
    legacy_small_batch = "legacy_small_batch"
    original_saved_tensor_offload = "original_saved_tensor_offload"
    original_workload_checkpoint = "original_workload_checkpoint"


class SearchModeOption(str, Enum):
    until_target = "until_target"
    bounded_pareto = "bounded_pareto"


class NumericalRequirementOption(str, Enum):
    legacy = "legacy"
    exact_loss20 = "exact-loss20-v1"
    observed_bf16 = "observed-bf16-v1"


app = typer.Typer(help="Autoresearch for GPU memory.", no_args_is_help=True)


@app.command()
def version() -> None:
    """Show the installed version."""
    typer.echo(__version__)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def snapshot(
    ctx: typer.Context,
    script: Path,
    max_steps: int = typer.Option(20, min=1),
    max_seconds: float = typer.Option(120, min=0.01),
    seed: int = typer.Option(1337, min=0),
    device: str = typer.Option("cuda"),
    run_root: Annotated[Path | None, typer.Option()] = None,
    allocator_conf: str | None = typer.Option(None),
) -> None:
    """Capture a script in Docker; pass target arguments after --."""
    try:
        result = run_script(
            script,
            script_args=ctx.args,
            max_steps=max_steps,
            max_seconds=max_seconds,
            seed=seed,
            device=device,
            run_root=run_root,
            allocator_conf=allocator_conf,
        )
    except (OSError, ValueError) as error:
        typer.echo(f"Snapshot failed: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(
        json.dumps(
            {
                key: result.get(key)
                for key in (
                    "run_id",
                    "status",
                    "reason",
                    "run_dir",
                    "artifact_dir",
                    "cleanup_verified",
                )
            },
            indent=2,
        )
    )
    if result["status"] not in {"completed", "oom"}:
        raise typer.Exit(1)


@app.command()
def evidence(run_id: str, budget: int = typer.Option(150000, min=1)) -> None:
    """Build a bounded evidence prompt from a run ID or local run directory."""
    from headroom.evidence import build_evidence
    from headroom.lab.runner import PROJECT_ROOT

    candidate = Path(run_id)
    if not candidate.is_dir():
        candidate = PROJECT_ROOT / "runs" / run_id
    if not candidate.is_dir():
        typer.echo("Run directory not found; provide its full path or ID under runs/.", err=True)
        raise typer.Exit(1)
    try:
        result = build_evidence(candidate, budget=budget)
    except (OSError, ValueError, TypeError) as error:
        typer.echo(f"Evidence failed: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(
        json.dumps(
            {
                key: result.get(key)
                for key in (
                    "evidence_md",
                    "evidence_json",
                    "evidence_png",
                    "token_count",
                    "budget",
                    "source_token_count",
                )
            },
            indent=2,
        )
    )


@app.command()
def diagnose(
    snapshot: Annotated[Path, typer.Option("--snapshot", exists=True, dir_okay=False)],
    traceback: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    source: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    budget: str = "0.30",
    runtime_profile: Path | None = None,
    run_root: Path | None = None,
) -> None:
    """Diagnose a saved CUDA snapshot and suggest an unverified patch; never run the source."""
    from headroom.lab.runner import PROJECT_ROOT
    from headroom.snapshot_diagnosis import SnapshotDiagnosisRequest, run_snapshot_diagnosis

    output_root = run_root or PROJECT_ROOT / "runs/uploads"
    try:
        result = run_snapshot_diagnosis(
            SnapshotDiagnosisRequest(
                snapshot=snapshot,
                traceback=traceback,
                source=source,
                budget_usd=budget,
                runtime_profile=runtime_profile,
            ),
            run_root=output_root,
        )
    except (OSError, ValueError):
        typer.echo(
            "Snapshot diagnosis could not start. Check the input and runtime configuration.",
            err=True,
        )
        raise typer.Exit(1) from None
    directory = output_root.resolve() / result["run_id"]
    typer.echo(
        json.dumps(
            {
                "run_id": result["run_id"],
                "status": result["status"],
                "verification": result["verification"],
                "provenance": result["provenance"],
                "cost_usd": result["cost_usd"],
                "error": result["error"],
                "diagnosis_json": str(directory / "diagnosis.json"),
                "diagnosis_markdown": str(directory / "diagnosis.md"),
                "patch": str(directory / "patch.diff")
                if result["patch"]["status"] == "unverified"
                else None,
            },
            indent=2,
        )
    )
    if result["status"] not in {"completed", "needs_human"}:
        raise typer.Exit(1)


def main() -> None:
    from headroom.cli_execution import load_context

    execution = load_context()
    if execution is None:
        app()
        return
    try:
        try:
            app(obj=execution)
        except SystemExit as error:
            code = error.code if type(error.code) is int else 0 if error.code is None else 1
            execution.finish(code, returned=True)
            raise
        except BaseException:
            execution.finish(None, returned=False)
            raise
        else:
            execution.finish(0, returned=True)
    finally:
        execution.close()


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def fix(
    ctx: typer.Context,
    script: Annotated[Path | None, typer.Argument()] = None,
    target: str = typer.Option("fix-oom"),
    reclaim_reduction_pct: float = typer.Option(30, min=0, max=100),
    allow_numerics_change: bool = False,
    numerical_requirement: NumericalRequirementOption = NumericalRequirementOption.legacy,
    allow_batch_grad_accum: bool = True,
    max_throughput_regression_pct: float = typer.Option(25, min=0, max=1000),
    config: Annotated[
        Path | None, typer.Option(help="Project YAML; CLI settings take precedence.")
    ] = None,
    max_steps: int = typer.Option(20, min=1, max=10000),
    max_seconds: int = typer.Option(120, min=1, max=3600),
    budget: str = "0.6",
    daily_budget: str = "12",
    device: str = "cuda",
    seed: int = 1337,
    source_root: Path | None = None,
    runtime_profile: Path | None = None,
    repo: str | None = None,
    ref: str | None = None,
    cmd: str | None = None,
    max_rounds: int = typer.Option(6, min=1, max=6),
    search_mode: SearchModeOption = SearchModeOption.until_target,
    research: bool = True,
    allocator_conf: str | None = typer.Option(
        None,
        help="Allowlisted allocator options; an explicit empty string clears project configuration.",
    ),
    reference_strategy: ReferenceStrategyOption = ReferenceStrategyOption.legacy_small_batch,
    reference_cpu_bytes: int = typer.Option(16 * 1024**3, min=1, max=16 * 1024**3),
    reference_disk_bytes: int = typer.Option(0, min=0, max=64 * 1024**3),
    reference_max_seconds: int = typer.Option(
        0,
        min=0,
        max=480,
        help="Reference timeout; 0 uses the normal Lab timeout. The outer run deadline still applies.",
    ),
) -> None:
    """Run the complete repair pipeline; missing live prerequisites produce a partial report."""
    from rich.console import Console

    from headroom.cli_execution import CLIExecution
    from headroom.orchestrator import FixRequest, Policy, run_fix
    from headroom.project_config import (
        ProjectConfig,
        ProjectConfigError,
        configured_script,
        find_project_config,
        load_project_config,
    )

    console = Console(stderr=True, markup=False)
    execution = ctx.obj if isinstance(ctx.obj, CLIExecution) else None
    try:
        config_path = find_project_config(
            config, script=script, source_root=source_root, remote_repository=repo is not None
        )
        project = load_project_config(config_path) if config_path else ProjectConfig()

        def explicit(name):
            # Typer may use its bundled Click enum; compare the public source name.
            return getattr(ctx.get_parameter_source(name), "name", None) == "COMMANDLINE"

        def selected(name, value):
            if explicit(name):
                return value
            return getattr(project, name) if name in project.model_fields_set else value

        reference = project.numerical_reference.model_dump()
        for name, field, value in (
            ("reference_strategy", "strategy", reference_strategy.value),
            ("reference_cpu_bytes", "cpu_saved_tensor_limit_bytes", reference_cpu_bytes),
            ("reference_disk_bytes", "disk_saved_tensor_limit_bytes", reference_disk_bytes),
            ("reference_max_seconds", "max_seconds", reference_max_seconds or None),
        ):
            if explicit(name):
                reference[field] = value
        numerical_reference = NumericalReference.model_validate(reference)
        allocator = validate_allocator(
            (allocator_conf or None) if explicit("allocator_conf") else project.allocator_conf
        )

        policy = project.policy.model_dump()
        for name, value in (
            ("allow_numerics_change", allow_numerics_change),
            ("numerical_requirement", numerical_requirement.value),
            ("allow_batch_grad_accum", allow_batch_grad_accum),
            ("max_throughput_regression_pct", max_throughput_regression_pct),
        ):
            if explicit(name):
                policy[name] = value

        profile, execution_argv = None, None
        repository_mode = False
        arguments = list(ctx.args)
        if repo is not None:
            if script is not None or source_root is not None or arguments or not ref or not cmd:
                raise ValueError("Repository input needs --repo/--ref/--cmd only")
            from headroom.repository import prepare_repository

            options = execution.repository_options(repo, ref, cmd) if execution else {}
            prepared = prepare_repository(repo, ref, cmd, **options)
            if execution:
                execution.repository_prepared(prepared)
            script, source_root = prepared.script, prepared.source_root
            arguments, profile = list(prepared.script_args), prepared.source_profile
            execution_argv = list(prepared.execution_argv)
            repository_mode = True
        elif cmd is not None:
            if script is not None or source_root is None or arguments or ref is not None:
                raise ValueError("Local command input needs --source-root/--cmd only")
            from headroom.repository import prepare_local_command

            prepared = prepare_local_command(source_root, cmd)
            script, source_root = prepared.script, prepared.source_root
            arguments = list(prepared.script_args)
            execution_argv = list(prepared.execution_argv)
            repository_mode = True
        else:
            if ref is not None:
                raise ValueError("--ref needs --repo/--cmd")
            if script is None and config_path is not None:
                script = configured_script(project, config_path)
                if script is not None and source_root is None:
                    source_root = config_path.parent.resolve()
            if script is None:
                raise ValueError("Supply a script, a configured script, or a repository command")
            if not arguments:
                arguments = project.script_args
        request = FixRequest(
            script=str(script),
            source_root=str(source_root) if source_root else None,
            script_args=arguments,
            execution_argv=execution_argv,
            repository_mode=repository_mode,
            target=selected("target", target),
            reclaim_reduction_pct=selected("reclaim_reduction_pct", reclaim_reduction_pct),
            policy=Policy(**policy),
            numerical_reference=numerical_reference,
            allocator_conf=allocator,
            max_steps=selected("max_steps", max_steps),
            max_seconds=selected("max_seconds", max_seconds),
            seed=selected("seed", seed),
            budget_usd=budget,
            daily_budget_usd=daily_budget,
            device=selected("device", device),
            runtime_profile=str(runtime_profile) if runtime_profile else None,
            source_profile=profile,
            max_rounds=selected("max_rounds", max_rounds),
            search_mode=selected("search_mode", search_mode.value),
            research_enabled=research,
        )
        result = run_fix(
            request,
            on_event=lambda event: console.print(f"{event['sequence']:02d} {event['kind']}"),
            **(execution.before_run(request) if execution else {}),
        )
        if execution:
            execution.save_result(result)
    except (OSError, ValueError, TypeError) as error:
        detail = str(error) if isinstance(error, ProjectConfigError) else type(error).__name__
        typer.echo("Fix request failed: " + detail, err=True)
        raise typer.Exit(1) from None
    typer.echo(
        json.dumps({key: value for key, value in result.items() if key != "report"}, indent=2)
    )
    if result["status"] in {"needs_human", "budget_exceeded"}:
        raise typer.Exit(78)
    if result["status"] == "timeout":
        raise typer.Exit(124)
    if result["status"] != "completed":
        raise typer.Exit(1)


def _store():
    from headroom.lab.runner import PROJECT_ROOT
    from headroom.store.db import Store

    return Store(PROJECT_ROOT / "runs/headroom.db")


@app.command()
def usage(run_id: str | None = None) -> None:
    """Show persisted usage; unknown costs are never reported as zero."""
    store = _store()
    try:
        typer.echo(json.dumps(store.usage(run_id), indent=2))
    finally:
        store.close()


@app.command()
def report(run_id: str) -> None:
    """Print an existing report by its durable run ID."""
    store = _store()
    try:
        row = store.get_run(run_id)
        if row is None:
            raise typer.BadParameter("Unknown run ID")
        path = Path(row["run_dir"]) / "report.md"
        if not path.is_file():
            typer.echo("Report has not been generated yet.", err=True)
            raise typer.Exit(78)
        typer.echo(path.read_text())
    finally:
        store.close()


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, runtime_profile: Path | None = None) -> None:
    """Serve the local app. Public deployment requires its separate setup."""
    import uvicorn

    from headroom.api.app import ApiSettings, create_app

    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise typer.BadParameter("Use the reviewed deployment configuration for public binding")
    settings = ApiSettings(runtime_profile=str(runtime_profile) if runtime_profile else None)
    uvicorn.run(create_app(settings), host=host, port=port, proxy_headers=False)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def watch(
    ctx: typer.Context,
    source_root: Path | None = None,
    target: str = "fix-oom",
    max_steps: int = typer.Option(20, min=1, max=10000),
    max_seconds: int = typer.Option(120, min=1, max=3600),
    device: str = "cuda",
    seed: int = 1337,
    budget: str = "0.6",
    daily_budget: str = "12",
    runtime_profile: Path | None = None,
    allocator_conf: str | None = typer.Option(
        None,
        help="Allowlisted options applied to Watch baseline and repair; empty clears project configuration.",
    ),
    allow_numerics_change: bool = False,
    search_mode: SearchModeOption = SearchModeOption.until_target,
    config: Annotated[
        Path | None, typer.Option(help="Project YAML; CLI settings take precedence.")
    ] = None,
) -> None:
    """Observe argv in Docker; confirmed CUDA OOM repairs mapped Python scripts.

    Shell wrappers retain their full argv. A single captured Python main supplies
    the source mapping; ambiguous/multiple or source-free entries need human input.
    """
    from headroom.orchestrator import Policy
    from headroom.project_config import find_project_config, load_project_config
    from headroom.watch import watch_command

    try:
        config_path = find_project_config(config, script=None, source_root=source_root)
        project = load_project_config(config_path) if config_path else None
        allocator = validate_allocator(
            (allocator_conf or None)
            if getattr(ctx.get_parameter_source("allocator_conf"), "name", None) == "COMMANDLINE"
            else project.allocator_conf
            if project
            else None
        )
        mode = search_mode.value
        if (
            project is not None
            and getattr(ctx.get_parameter_source("search_mode"), "name", None) != "COMMANDLINE"
        ):
            mode = project.search_mode
        result = watch_command(
            list(ctx.args),
            source_root=source_root or Path.cwd(),
            max_steps=max_steps,
            max_seconds=max_seconds,
            device=device,
            seed=seed,
            fix_options={
                "target": target,
                "search_mode": mode,
                "budget_usd": budget,
                "daily_budget_usd": daily_budget,
                "runtime_profile": str(runtime_profile) if runtime_profile else None,
                "policy": Policy(allow_numerics_change=allow_numerics_change),
                "allocator_conf": allocator,
                "numerical_reference": project.numerical_reference
                if project
                else NumericalReference(),
            },
        )
    except (OSError, ValueError, TypeError):
        typer.echo(
            "Watch requires supported Docker argv and a valid source directory; "
            "automatic repair needs one captured Python main inside that source.",
            err=True,
        )
        raise typer.Exit(2) from None
    for name, is_error in (("stdout_path", False), ("stderr_path", True)):
        if result.get(name):
            path = Path(result[name])
            if path.is_file():
                typer.echo(path.read_text(errors="replace"), err=is_error, nl=False)
    typer.echo(
        json.dumps(
            {
                k: result.get(k)
                for k in (
                    "status",
                    "search_mode",
                    "triggered",
                    "capture_status",
                    "cuda_oom_confirmed",
                    "repair_supported",
                    "repair_unavailable_reason",
                    "reason",
                    "exit_code",
                    "original_exit_code",
                    "report_path",
                    "watch_report_path",
                    "stdout_path",
                    "stderr_path",
                )
            },
            indent=2,
        )
    )
    raise typer.Exit(result["exit_code"])


@app.command("eval")
def evaluate(
    manifest: Path | None = None,
    validate_only: bool = False,
    plan_only: bool = False,
    dry_run: bool = False,
    live: bool = False,
    scenario: Annotated[list[str] | None, typer.Option()] = None,
    conditions: str = "full_ultra",
    policies: str = "default",
    search_mode: SearchModeOption | None = None,
    study_protocol: str | None = None,
    budget: str = "0.6",
    campaign_budget: str = "0.6",
    daily_budget: str = "12",
    runtime_profile: Path | None = None,
    device: str = "cuda",
    max_seconds: int = typer.Option(120, min=1, max=3600),
) -> None:
    """Validate, plan policies, run real baselines (--dry-run), or an explicitly live campaign."""
    from headroom.evaluation import (
        campaign_plan,
        execute_baselines,
        run_campaign,
        validate_manifest,
    )
    from headroom.lab.runner import PROJECT_ROOT

    if sum((validate_only, plan_only, dry_run, live)) != 1:
        raise typer.BadParameter("Choose one: --validate-only, --plan-only, --dry-run, or --live")
    if live and device != "cuda":
        raise typer.BadParameter("Live campaigns currently use CUDA; --device applies to baselines")
    if live and max_seconds != 120:
        raise typer.BadParameter("Live campaigns use the reviewed 120-second Lab limit")
    if not (live or plan_only) and (conditions != "full_ultra" or policies != "default"):
        raise typer.BadParameter("--conditions/--policies apply only to --plan-only or --live")
    if search_mode is not None and not (live or plan_only):
        raise typer.BadParameter("--search-mode applies only to --plan-only or --live")
    if study_protocol is not None and not (live or plan_only):
        raise typer.BadParameter("--study-protocol applies only to --plan-only or --live")
    path = manifest or PROJECT_ROOT / "eval/scenario_set.yaml"
    try:
        if validate_only:
            result = validate_manifest(path)
        elif plan_only:
            result = campaign_plan(
                path,
                scenario_ids=scenario,
                conditions=tuple(item.strip() for item in conditions.split(",")),
                policy_names=tuple(item.strip() for item in policies.split(",")),
                search_mode=search_mode.value if search_mode is not None else None,
                study_protocol=study_protocol,
                per_run_budget_usd=budget,
                campaign_budget_usd=campaign_budget,
                daily_budget_usd=daily_budget,
            )
        elif dry_run:
            result = execute_baselines(
                path, execute=True, device=device, scenario_ids=scenario, max_seconds=max_seconds
            )
        else:
            result = run_campaign(
                path,
                execute=True,
                live_authorized=True,
                runtime_profile=runtime_profile,
                scenario_ids=scenario,
                conditions=tuple(item.strip() for item in conditions.split(",")),
                policy_names=tuple(item.strip() for item in policies.split(",")),
                search_mode=search_mode.value if search_mode is not None else None,
                study_protocol=study_protocol,
                per_run_budget_usd=budget,
                campaign_budget_usd=campaign_budget,
                daily_budget_usd=daily_budget,
            )
    except (OSError, ValueError, TypeError) as error:
        typer.echo("Evaluation could not proceed: " + type(error).__name__, err=True)
        raise typer.Exit(78) from None
    typer.echo(json.dumps(result, indent=2))
    if validate_only and result.get("status") != "valid":
        raise typer.Exit(78)
    if dry_run and not (
        result.get("accepted") is True or result.get("selected_baselines_passed") is True
    ):
        raise typer.Exit(1)
    if live and (
        result.get("status") != "finished"
        or any(row.get("status") != "completed" for row in result.get("rows", []))
    ):
        raise typer.Exit(1)


scope_app = typer.Typer(
    help="Inspect exact historical repair conditions; never runs a model or target.",
    no_args_is_help=True,
)
app.add_typer(scope_app, name="scope")


@scope_app.command("build")
def scope_build(
    specification: Path,
    evidence_root: Annotated[
        Path, typer.Option(help="Trusted local archive containing selected jobs.")
    ],
    output: Annotated[
        Path, typer.Option(help="New JSON file; existing files are never overwritten.")
    ],
) -> None:
    """Bind selected historical repair rounds to their measured conditions."""
    from headroom.verify.applicability import build_scope, load_json

    try:
        document = load_json(specification)
        if not isinstance(document, dict) or set(document) != {"selections"}:
            raise ValueError("Specification must contain only selections")
        result = build_scope(evidence_root, document["selections"])
        encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
        with output.open("x") as handle:
            handle.write(encoded)
    except (OSError, ValueError, TypeError) as error:
        typer.echo("Scope build failed: " + type(error).__name__, err=True)
        raise typer.Exit(78) from None
    typer.echo(json.dumps({"output": str(output), "observations": len(result["observations"])}))


@scope_app.command("check")
def scope_check(
    record: Path,
    query: Path,
    evidence_root: Annotated[
        Path, typer.Option(help="Same trusted archive used to build the record.")
    ],
) -> None:
    """Recheck evidence and look up an exact context; untested conditions remain unknown."""
    from headroom.verify.applicability import check_scope, load_json

    try:
        result = check_scope(evidence_root, load_json(record), load_json(query))
    except (OSError, ValueError, TypeError):
        result = {"status": "invalid_evidence", "reasons": ["Scope/query could not be read"]}
    typer.echo(json.dumps(result, indent=2, allow_nan=False))
    if result["status"] != "tested_pass":
        raise typer.Exit(78)
