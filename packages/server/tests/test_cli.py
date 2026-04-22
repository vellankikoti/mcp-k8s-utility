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
