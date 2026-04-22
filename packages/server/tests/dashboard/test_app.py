from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from utility_server.dashboard.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_index_renders(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "mcp-k8s-utility" in r.text
    # tiles must be wired to HTMX endpoints
    assert "/tiles/system-health" in r.text
    assert "/tiles/llm-provider" in r.text
    assert "/tiles/tool-activity" in r.text


def test_system_health_tile_handles_unconfigured(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("SECUREOPS_OPA_URL", raising=False)
    monkeypatch.delenv("PROMETHEUS_URL", raising=False)
    monkeypatch.delenv("OPENSEARCH_URL", raising=False)
    monkeypatch.delenv("SECUREOPS_AUDIT_DB", raising=False)
    r = client.get("/tiles/system-health")
    assert r.status_code == 200
    assert "unconfigured" in r.text
    assert "opa" in r.text
    assert "prometheus" in r.text


def test_llm_provider_tile_default(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("UTILITY_LLM_PROVIDER", raising=False)
    r = client.get("/tiles/llm-provider")
    assert r.status_code == 200
    assert "disabled" in r.text


def test_llm_provider_tile_invalid_value(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("UTILITY_LLM_PROVIDER", "bogus")
    r = client.get("/tiles/llm-provider")
    assert r.status_code == 200
    assert "error" in r.text.lower()
    assert "bogus" in r.text


def test_tool_activity_tile_empty(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("SECUREOPS_AUDIT_DB", "/nonexistent/path.db")
    r = client.get("/tiles/tool-activity")
    assert r.status_code == 200
    assert "No audit rows yet" in r.text


def test_tool_activity_tile_with_rows(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    import asyncio

    import aiosqlite

    db = tmp_path / "audit.db"

    async def _setup() -> None:
        async with aiosqlite.connect(str(db)) as conn:
            await conn.execute(
                """CREATE TABLE audit_rows (
                       row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                       action_id TEXT NOT NULL,
                       prev_hash TEXT NOT NULL,
                       row_hash TEXT NOT NULL,
                       payload_json TEXT NOT NULL,
                       created_at TEXT NOT NULL
                   )"""
            )
            payload = {
                "proposal": {"tool_name": "restart_deployment"},
                "result": {"status": "allowed_executed", "opa_decision": {"allow": True}},
            }
            await conn.execute(
                "INSERT INTO audit_rows(action_id, prev_hash, row_hash, payload_json, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                ("a1", "0" * 64, "a" * 64, json.dumps(payload), "2026-04-22T10:00:00+00:00"),
            )
            await conn.commit()

    asyncio.run(_setup())
    monkeypatch.setenv("SECUREOPS_AUDIT_DB", str(db))
    r = client.get("/tiles/tool-activity")
    assert r.status_code == 200
    assert "restart_deployment" in r.text
    assert "allowed_executed" in r.text


def test_opa_decisions_tile_empty(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECUREOPS_AUDIT_DB", "/nonexistent/path.db")
    r = client.get("/tiles/opa-decisions")
    assert r.status_code == 200
    assert "No audit rows" in r.text


def test_opa_decisions_tile_with_denial(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    import aiosqlite

    db = tmp_path / "audit.db"

    async def _seed() -> None:
        async with aiosqlite.connect(str(db)) as conn:
            await conn.execute(
                """CREATE TABLE audit_rows (
                       row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                       action_id TEXT NOT NULL, prev_hash TEXT NOT NULL,
                       row_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
                       created_at TEXT NOT NULL
                   )"""
            )
            payload = {
                "proposal": {"tool_name": "scale_workload"},
                "result": {
                    "status": "denied_opa",
                    "opa_decision": {"allow": False, "reasons": ["prod_scale_zero_denied"]},
                },
            }
            await conn.execute(
                "INSERT INTO audit_rows(action_id,prev_hash,row_hash,payload_json,created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                ("d1", "0" * 64, "b" * 64, json.dumps(payload), "2026-04-22T11:00:00+00:00"),
            )
            await conn.commit()

    asyncio.run(_seed())
    monkeypatch.setenv("SECUREOPS_AUDIT_DB", str(db))
    r = client.get("/tiles/opa-decisions")
    assert r.status_code == 200
    assert "scale_workload" in r.text
    assert "prod_scale_zero_denied" in r.text
    assert "denied_opa" in r.text


def test_per_action_sas_unconfigured(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KUBECONFIG", "/nonexistent/path")
    r = client.get("/tiles/per-action-sas")
    assert r.status_code == 200
    assert "unconfigured" in r.text.lower() or "no kubeconfig" in r.text.lower()


def test_demo_runner_tile(client: TestClient) -> None:
    r = client.get("/tiles/demo-runner")
    assert r.status_code == 200
    assert "List evicted pods" in r.text
    assert "Propose cleanup plan" in r.text
    assert "Propose alert tuning" in r.text


def test_demo_unknown_404(client: TestClient) -> None:
    r = client.post("/actions/demo/bogus")
    assert r.status_code == 404


def test_demo_alert_tuning_returns_json_with_ok_field(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No Prometheus configured → list_noisy_alerts returns []; report has 0 findings.
    monkeypatch.delenv("PROMETHEUS_URL", raising=False)
    monkeypatch.delenv("UTILITY_LLM_PROVIDER", raising=False)
    r = client.post("/actions/demo/alert-tuning")
    assert r.status_code == 200
    body = json.loads(r.text)
    assert body["ok"] is True
    assert body["findings"] == 0


def test_index_includes_new_tiles(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "/tiles/opa-decisions" in r.text
    assert "/tiles/per-action-sas" in r.text
    assert "/tiles/demo-runner" in r.text
