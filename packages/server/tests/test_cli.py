from __future__ import annotations

from typer.testing import CliRunner
from utility_server.cli import app

runner = CliRunner()


def test_cli_version_prints_package_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_cli_has_serve_mcp_command():
    result = runner.invoke(app, ["serve-mcp", "--help"])
    assert result.exit_code == 0
    assert "mcp" in result.stdout.lower() or "stdio" in result.stdout.lower()


def test_cli_has_llm_probe_command():
    result = runner.invoke(app, ["llm-probe", "--help"])
    assert result.exit_code == 0
    assert "llm" in result.stdout.lower() or "probe" in result.stdout.lower()


def test_cli_llm_probe_disabled_prints_noop(monkeypatch):
    # With no UTILITY_LLM_PROVIDER set, adapter is DISABLED and narrate returns None.
    monkeypatch.delenv("UTILITY_LLM_PROVIDER", raising=False)
    result = runner.invoke(app, ["llm-probe"])
    assert result.exit_code == 0
    assert "disabled" in result.stdout.lower()
    assert "none" in result.stdout.lower() or "fallback" in result.stdout.lower()
