from __future__ import annotations

import typer

from utility_server import __version__
from utility_server.mcp_server import run_stdio

app = typer.Typer(
    name="mcp-k8s-utility",
    help="AI-assisted Kubernetes toil elimination via MCP.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command("serve-mcp")
def serve_mcp() -> None:
    """Run the MCP server over stdio."""
    run_stdio()
