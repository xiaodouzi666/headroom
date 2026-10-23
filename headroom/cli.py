"""Headroom command-line entry point. Runtime commands arrive in Phase 1."""

import typer

from headroom import __version__

app = typer.Typer(help="Autoresearch for GPU memory.", no_args_is_help=True)


@app.command()
def version() -> None:
    """Show the installed version."""
    typer.echo(__version__)


def main() -> None:
    app()
