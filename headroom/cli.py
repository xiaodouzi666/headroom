"""Headroom command-line entry point."""

import json
from pathlib import Path
from typing import Annotated

import typer

from headroom import __version__
from headroom.lab.runner import run_script

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


def main() -> None:
    app()
