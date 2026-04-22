from __future__ import annotations

import asyncio
import os

import typer

from utility_server import __version__
from utility_server.llm.adapter import UtilityLLM
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
def serve_mcp(
    provider: str = typer.Option(
        "",
        "--provider",
        "-p",
        help="LLM provider: vertex | anthropic | openai | ollama | disabled.",
    ),
) -> None:
    """Run the MCP server over stdio."""
    if provider:
        os.environ["UTILITY_LLM_PROVIDER"] = provider
    run_stdio()


@app.command("llm-probe")
def llm_probe(
    provider: str = typer.Option(
        "",
        "--provider",
        "-p",
        help="LLM provider to probe.",
    ),
) -> None:
    """Send a 1-sentence prompt to the configured LLM; print the response or 'no-op'."""
    if provider:
        os.environ["UTILITY_LLM_PROVIDER"] = provider

    async def _run() -> None:
        llm = UtilityLLM.from_env()
        typer.echo(f"provider: {llm.provider_name}")
        out = await llm.narrate(
            "In one sentence, say hello from the configured provider.",
            {"context": "cli-probe"},
        )
        typer.echo(f"response: {out if out else '(none — fallback path)'}")

    asyncio.run(_run())
