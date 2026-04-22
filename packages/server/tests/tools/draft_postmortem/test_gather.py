from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from utility_server.models import PostmortemSources
from utility_server.opensearch_client import OpenSearchClient
from utility_server.prom_client import PromClient
from utility_server.tools.draft_postmortem.gather import (
    _gather_audit,
    _gather_events,
    _gather_logs,
    _gather_prometheus,
    compute_window,
    gather_postmortem_sources,
)


def _event(reason: str, minutes_ago: float, type_: str = "Warning"):
    e = MagicMock()
    e.last_timestamp = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    e.type = type_
    e.reason = reason
    e.message = f"{reason} happened"
    e.involved_object.kind = "Pod"
    e.involved_object.name = "checkout-xyz"
    e.involved_object.namespace = "prod"
    return e


def test_compute_window_returns_tuple():
    start, end = compute_window(minutes_back=30)
    assert (end - start).total_seconds() == 30 * 60


async def test_gather_events_filters_by_window():
    core = MagicMock()
    core.list_namespaced_event = AsyncMock(
        return_value=MagicMock(
            items=[
                _event("InWindow", minutes_ago=5),
                _event("TooOld", minutes_ago=60),
            ]
        )
    )
    start = datetime.now(UTC) - timedelta(minutes=15)
    end = datetime.now(UTC)
    events, src = await _gather_events(core, namespace="prod", start=start, end=end)
    assert src == "k8s"
    assert {e.reason for e in events} == {"InWindow"}


async def test_gather_events_no_cluster():
    events, src = await _gather_events(
        None,
        namespace=None,
        start=datetime.now(UTC) - timedelta(minutes=1),
        end=datetime.now(UTC),
    )
    assert events == []
    assert src == "unconfigured"


async def test_gather_events_unavailable_on_exception():
    core = MagicMock()
    core.list_event_for_all_namespaces = AsyncMock(side_effect=RuntimeError("down"))
    events, src = await _gather_events(
        core,
        namespace=None,
        start=datetime.now(UTC) - timedelta(minutes=1),
        end=datetime.now(UTC),
    )
    assert events == []
    assert src == "unavailable"


async def test_gather_prometheus_unconfigured_returns_unavailable_samples():
    prom = PromClient(base_url=None)
    samples = await _gather_prometheus(prom)
    assert len(samples) == 2
    assert all(s.source == "unavailable" for s in samples)
    assert all(s.value is None for s in samples)


async def test_gather_prometheus_configured_queries_both_metrics():
    class _P(PromClient):
        def __init__(self) -> None:
            super().__init__(base_url="http://stub")
            self._q: list[str] = []

        async def instant(self, expr: str):  # type: ignore[override]
            self._q.append(expr)
            return [{"value": [0, "0.05"]}] if "5.." in expr else [{"value": [0, "230"]}]

    prom = _P()
    samples = await _gather_prometheus(prom)
    assert len(samples) == 2
    assert samples[0].name == "error_rate_5m"
    assert samples[0].value == 0.05
    assert samples[1].name == "p99_latency_5m_ms"
    assert samples[1].value == 230.0


async def test_gather_logs_unconfigured():
    client = OpenSearchClient(base_url=None)
    out = await _gather_logs(
        client=client,
        start=datetime.now(UTC) - timedelta(minutes=30),
        end=datetime.now(UTC),
        namespace=None,
    )
    assert out.source == "unconfigured"
    assert out.total == 0


async def test_gather_audit_unconfigured(monkeypatch):
    monkeypatch.delenv("SECUREOPS_AUDIT_DB", raising=False)
    rows, src = await _gather_audit(datetime.now(UTC) - timedelta(minutes=30), datetime.now(UTC))
    assert rows == []
    assert src == "unconfigured"


async def test_gather_audit_reads_rows_in_window(tmp_path, monkeypatch):
    import json as _json

    import aiosqlite

    db = tmp_path / "audit.db"
    async with aiosqlite.connect(str(db)) as conn:
        await conn.execute(
            """CREATE TABLE audit_rows (
                   row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                   action_id TEXT NOT NULL, prev_hash TEXT NOT NULL,
                   row_hash TEXT NOT NULL, payload_json TEXT NOT NULL,
                   created_at TEXT NOT NULL
               )"""
        )
        payload_allow = {
            "proposal": {"tool_name": "restart_deployment"},
            "result": {
                "status": "allowed_executed",
                "opa_decision": {"allow": True, "reasons": []},
            },
        }
        payload_deny = {
            "proposal": {"tool_name": "scale_workload"},
            "result": {
                "status": "denied_opa",
                "opa_decision": {"allow": False, "reasons": ["prod_scale_zero_denied"]},
            },
        }
        in_window = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        out_of_window = (datetime.now(UTC) - timedelta(minutes=60)).isoformat()
        await conn.executemany(
            "INSERT INTO audit_rows(action_id,prev_hash,row_hash,payload_json,created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                ("a1", "0" * 64, "a" * 64, _json.dumps(payload_allow), in_window),
                ("d1", "0" * 64, "b" * 64, _json.dumps(payload_deny), in_window),
                ("o1", "0" * 64, "c" * 64, _json.dumps(payload_allow), out_of_window),
            ],
        )
        await conn.commit()

    monkeypatch.setenv("SECUREOPS_AUDIT_DB", str(db))
    rows, src = await _gather_audit(datetime.now(UTC) - timedelta(minutes=30), datetime.now(UTC))
    assert src == "sqlite"
    assert len(rows) == 2
    denial = next(r for r in rows if r.status == "denied_opa")
    assert denial.opa_reasons == ["prod_scale_zero_denied"]


async def test_gather_postmortem_sources_wires_everything(monkeypatch):
    monkeypatch.delenv("SECUREOPS_AUDIT_DB", raising=False)
    core = MagicMock()
    core.list_event_for_all_namespaces = AsyncMock(return_value=MagicMock(items=[]))
    prom = PromClient(base_url=None)
    osearch = OpenSearchClient(base_url=None)
    start = datetime.now(UTC) - timedelta(minutes=30)
    end = datetime.now(UTC)
    out: PostmortemSources = await gather_postmortem_sources(
        core_v1=core,
        prom=prom,
        opensearch=osearch,
        start=start,
        end=end,
        namespace=None,
    )
    assert out.events_source == "k8s"
    assert all(s.source == "unavailable" for s in out.prometheus_samples)
    assert out.logs.source == "unconfigured"
    assert out.audit_source == "unconfigured"
