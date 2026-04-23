from __future__ import annotations

from typer.testing import CliRunner
from utility_server.cli import app

runner = CliRunner()


def test_cli_version_prints_package_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.5.0" in result.stdout


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


def test_cli_llm_probe_invalid_provider_exits_cleanly(monkeypatch):
    monkeypatch.setenv("UTILITY_LLM_PROVIDER", "bogus")
    result = runner.invoke(app, ["llm-probe"])
    assert result.exit_code == 1
    # Error message surfaces via stderr (typer merges it into output by default in CliRunner)
    combined = (result.stdout or "") + (result.stderr or "")
    assert "bogus" in combined.lower() or "not recognized" in combined.lower()
    # And no raw Traceback leaked
    assert "Traceback" not in combined


def test_cli_has_dashboard_command():
    result = runner.invoke(app, ["dashboard", "--help"])
    assert result.exit_code == 0
    out = result.stdout.lower()
    assert "dashboard" in out or "htmx" in out or "fastapi" in out or "http" in out
