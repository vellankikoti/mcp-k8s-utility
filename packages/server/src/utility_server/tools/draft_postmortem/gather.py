from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import aiosqlite

from utility_server.models import (
    AuditRowSummary,
    LogBucket,
    LogsSummary,
    PostmortemEvent,
    PostmortemSources,
    PrometheusSample,
)
from utility_server.opensearch_client import OpenSearchClient
from utility_server.prom_client import PromClient


def _coerce_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


async def _gather_events(
    core_v1: Any, namespace: str | None, start: datetime, end: datetime
) -> tuple[list[PostmortemEvent], str]:
    if core_v1 is None:
        return [], "unconfigured"
    try:
        if namespace:
            resp = await core_v1.list_namespaced_event(namespace=namespace)
        else:
            resp = await core_v1.list_event_for_all_namespaces()
    except Exception:
        return [], "unavailable"
    out: list[PostmortemEvent] = []
    for e in getattr(resp, "items", None) or []:
        ts = _coerce_dt(getattr(e, "last_timestamp", None))
        if ts is None:
            continue
        if ts < start or ts > end:
            continue
        involved = getattr(e, "involved_object", None)
        out.append(
            PostmortemEvent(
                timestamp=ts,
                type=getattr(e, "type", "") or "",
                reason=getattr(e, "reason", "") or "",
                message=(getattr(e, "message", "") or "")[:300],
                involved_kind=getattr(involved, "kind", None) if involved else None,
                involved_name=getattr(involved, "name", None) if involved else None,
                involved_namespace=getattr(involved, "namespace", None) if involved else None,
            )
        )
    out.sort(key=lambda p: p.timestamp or start, reverse=True)
    return out[:50], "k8s"


async def _gather_prometheus(prom: PromClient) -> list[PrometheusSample]:
    queries = [
        (
            "error_rate_5m",
            'sum(rate(http_requests_total{code=~"5.."}[5m])) / '
            "clamp_min(sum(rate(http_requests_total[5m])), 1)",
        ),
        (
            "p99_latency_5m_ms",
            "histogram_quantile(0.99, sum by (le) ("
            "rate(http_request_duration_seconds_bucket[5m]))) * 1000",
        ),
    ]
    samples: list[PrometheusSample] = []
    if not prom.configured:
        for name, _ in queries:
            samples.append(PrometheusSample(name=name, value=None, source="unavailable"))
        return samples
    for name, expr in queries:
        result = await prom.instant(expr)
        value = prom.first_value(result, default=float("nan")) if result else None
        if value is not None and value != value:  # NaN check
            value = None
        samples.append(
            PrometheusSample(
                name=name,
                value=value,
                source="prometheus" if result else "unavailable",
            )
        )
    return samples


async def _gather_logs(
    client: OpenSearchClient, start: datetime, end: datetime, namespace: str | None
) -> LogsSummary:
    if not client.configured:
        return LogsSummary(total=0, buckets=[], source="unconfigured")
    body: dict[str, Any] = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"range": {"@timestamp": {"gte": start.isoformat(), "lte": end.isoformat()}}},
                    {"match": {"level": "error"}},
                ]
            }
        },
        "aggs": {
            "by_minute": {
                "date_histogram": {
                    "field": "@timestamp",
                    "fixed_interval": "1m",
                    "min_doc_count": 1,
                }
            }
        },
    }
    if namespace:
        body["query"]["bool"]["must"].append({"match": {"kubernetes.namespace_name": namespace}})
    r = await client._request("POST", "/_search", json=body)
    if r is None:
        return LogsSummary(total=0, buckets=[], source="unavailable")
    try:
        data = r.json()
    except Exception:
        return LogsSummary(total=0, buckets=[], source="unavailable")
    hits = (data.get("hits") or {}).get("total") or {}
    total = int(hits.get("value") or 0) if isinstance(hits, dict) else int(hits or 0)
    aggs = data.get("aggregations") or {}
    buckets_raw = (aggs.get("by_minute") or {}).get("buckets") or []
    buckets: list[LogBucket] = []
    for b in buckets_raw[:30]:
        ts_ms = b.get("key")
        try:
            bucket_start = (
                datetime.fromtimestamp(int(ts_ms) / 1000, tz=UTC) if ts_ms is not None else None
            )
        except (TypeError, ValueError):
            bucket_start = None
        buckets.append(LogBucket(bucket_start=bucket_start, count=int(b.get("doc_count") or 0)))
    return LogsSummary(total=total, buckets=buckets, source="opensearch")


async def _gather_audit(
    start: datetime, end: datetime, limit: int = 200
) -> tuple[list[AuditRowSummary], str]:
    path = os.environ.get("SECUREOPS_AUDIT_DB", "")
    if not path:
        return [], "unconfigured"
    if not os.path.exists(path):
        return [], "unavailable"
    rows: list[AuditRowSummary] = []
    try:
        async with (
            aiosqlite.connect(path) as conn,
            conn.execute(
                "SELECT row_id, action_id, payload_json, created_at "
                "FROM audit_rows ORDER BY row_id DESC LIMIT ?",
                (limit,),
            ) as cur,
        ):
            async for row_id, action_id, payload_json, created_at in cur:
                ts = _coerce_dt(created_at)
                if ts is None or ts < start or ts > end:
                    continue
                try:
                    payload = json.loads(payload_json)
                except json.JSONDecodeError:
                    continue
                result = payload.get("result") or {}
                opa = result.get("opa_decision") or {}
                reasons = opa.get("reasons") or []
                rows.append(
                    AuditRowSummary(
                        row_id=row_id,
                        action_id=action_id,
                        tool=(payload.get("proposal") or {}).get("tool_name"),
                        status=result.get("status"),
                        opa_reasons=list(reasons) if isinstance(reasons, list) else [],
                        created_at=created_at,
                    )
                )
    except Exception:
        return [], "unavailable"
    return rows, "sqlite"


async def gather_postmortem_sources(
    *,
    core_v1: Any,
    prom: PromClient,
    opensearch: OpenSearchClient,
    start: datetime,
    end: datetime,
    namespace: str | None,
) -> PostmortemSources:
    events, events_source = await _gather_events(core_v1, namespace, start, end)
    prom_samples = await _gather_prometheus(prom)
    logs = await _gather_logs(opensearch, start, end, namespace)
    audit, audit_source = await _gather_audit(start, end)
    return PostmortemSources(
        events=events,
        events_source=events_source,  # type: ignore[arg-type]
        prometheus_samples=prom_samples,
        logs=logs,
        audit=audit,
        audit_source=audit_source,  # type: ignore[arg-type]
    )


def compute_window(*, minutes_back: int, now: datetime | None = None) -> tuple[datetime, datetime]:
    end = now or datetime.now(UTC)
    start = end - timedelta(minutes=minutes_back)
    return start, end
