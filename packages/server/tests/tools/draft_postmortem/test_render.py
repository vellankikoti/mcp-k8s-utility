from __future__ import annotations

from datetime import UTC, datetime, timedelta

from utility_server.llm.adapter import Provider, UtilityLLM
from utility_server.models import (
    AuditRowSummary,
    LogBucket,
    LogsSummary,
    PostmortemEvent,
    PostmortemSources,
    PrometheusSample,
)
from utility_server.tools.draft_postmortem.render import (
    render_markdown_fallback,
    render_postmortem_markdown,
)


def _sources(with_denial: bool = True) -> PostmortemSources:
    start = datetime.now(UTC) - timedelta(minutes=5)
    events = [
        PostmortemEvent(
            timestamp=start,
            type="Warning",
            reason="BackOff",
            message="Back-off restarting failed container",
            involved_kind="Pod",
            involved_name="checkout-xyz",
            involved_namespace="prod",
        )
    ]
    prom = [
        PrometheusSample(name="error_rate_5m", value=0.08, source="prometheus"),
        PrometheusSample(name="p99_latency_5m_ms", value=1230.0, source="prometheus"),
    ]
    logs = LogsSummary(
        total=42,
        buckets=[LogBucket(bucket_start=start, count=42)],
        source="opensearch",
    )
    audit = [
        AuditRowSummary(
            row_id=1,
            action_id="a1",
            tool="restart_deployment",
            status="allowed_executed",
            opa_reasons=[],
            created_at=start.isoformat(),
        )
    ]
    if with_denial:
        audit.append(
            AuditRowSummary(
                row_id=2,
                action_id="d1",
                tool="scale_workload",
                status="denied_opa",
                opa_reasons=["prod_scale_zero_denied"],
                created_at=start.isoformat(),
            )
        )
    return PostmortemSources(
        events=events,
        events_source="k8s",
        prometheus_samples=prom,
        logs=logs,
        audit=audit,
        audit_source="sqlite",
    )


def test_fallback_emits_all_sections():
    start = datetime.now(UTC) - timedelta(minutes=30)
    end = datetime.now(UTC)
    md = render_markdown_fallback(
        start=start,
        end=end,
        minutes=30,
        namespace="prod",
        workload="checkout",
        sources=_sources(),
    )
    for section in (
        "# Postmortem — checkout",
        "## Summary",
        "## Timeline",
        "## Impact",
        "## Logs (OpenSearch)",
        "## Audit trail",
        "## Action Items",
    ):
        assert section in md
    assert "BackOff" in md
    assert "error_rate_5m" in md
    assert "p99_latency_5m_ms" in md
    assert "denied_opa" in md
    assert "prod_scale_zero_denied" in md


def test_fallback_handles_missing_sources():
    start = datetime.now(UTC) - timedelta(minutes=30)
    end = datetime.now(UTC)
    empty = PostmortemSources(
        events=[],
        events_source="unavailable",
        prometheus_samples=[
            PrometheusSample(name="error_rate_5m", value=None, source="unavailable")
        ],
        logs=LogsSummary(total=0, buckets=[], source="unconfigured"),
        audit=[],
        audit_source="unconfigured",
    )
    md = render_markdown_fallback(
        start=start,
        end=end,
        minutes=30,
        namespace=None,
        workload=None,
        sources=empty,
    )
    assert "No events in window" in md
    assert "unavailable" in md
    assert "not configured" in md


async def test_render_postmortem_markdown_llm_disabled_yields_fallback():
    start = datetime.now(UTC) - timedelta(minutes=30)
    end = datetime.now(UTC)
    llm = UtilityLLM(Provider.DISABLED)
    md, narrated = await render_postmortem_markdown(
        llm=llm,
        start=start,
        end=end,
        minutes=30,
        namespace="prod",
        workload="checkout",
        sources=_sources(),
    )
    assert narrated is False
    assert "# Postmortem" in md
