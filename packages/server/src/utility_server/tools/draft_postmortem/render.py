from __future__ import annotations

from datetime import datetime

from utility_server.llm.adapter import UtilityLLM
from utility_server.models import PostmortemSources


def _format_event_line(
    ts: datetime | None,
    type_: str,
    reason: str,
    message: str,
    kind: str | None,
    name: str | None,
) -> str:
    when = ts.strftime("%H:%M:%S") if ts else "??:??:??"
    involved = f"{kind}/{name}" if kind and name else kind or name or "-"
    return f"- {when} — {type_}/{reason} — {message} (involved: {involved})"


def _format_logs(sources: PostmortemSources) -> str:
    logs = sources.logs
    if logs.source == "unconfigured":
        return "OpenSearch not configured (`OPENSEARCH_URL` unset)."
    if logs.source == "unavailable":
        return "OpenSearch unreachable during query window."
    if logs.total == 0:
        return "No error-level logs in window."
    bucket_lines = []
    for b in logs.buckets[:10]:
        ts = b.bucket_start.strftime("%H:%M") if b.bucket_start else "??:??"
        bucket_lines.append(f"  - {ts}: {b.count} entries")
    return f"{logs.total} error-level log entries in window:\n" + "\n".join(bucket_lines)


def _format_prometheus(sources: PostmortemSources) -> str:
    lines = []
    for s in sources.prometheus_samples:
        if s.source == "unavailable" or s.value is None:
            lines.append(f"- {s.name}: unavailable")
        else:
            lines.append(f"- {s.name}: {s.value:.4f}")
    return "\n".join(lines) if lines else "No Prometheus samples."


def _format_audit(sources: PostmortemSources) -> str:
    if sources.audit_source == "unconfigured":
        return "Audit ledger not configured (`SECUREOPS_AUDIT_DB` unset)."
    if sources.audit_source == "unavailable":
        return "Audit ledger unreachable."
    if not sources.audit:
        return "No audit rows in window."
    lines = []
    for r in sources.audit[:30]:
        reasons = (", ".join(r.opa_reasons)) if r.opa_reasons else ""
        reason_suffix = f" — reasons: {reasons}" if reasons else ""
        lines.append(f"- {r.created_at} — {r.tool or '?'}/{r.status or '?'}{reason_suffix}")
    return "\n".join(lines)


def render_markdown_fallback(
    *,
    start: datetime,
    end: datetime,
    minutes: int,
    namespace: str | None,
    workload: str | None,
    sources: PostmortemSources,
) -> str:
    scope = f"namespace={namespace or '(all)'}, workload={workload or '—'}"
    warn_count = sum(1 for e in sources.events if e.type == "Warning")
    info_count = len(sources.events) - warn_count
    denials = sum(1 for a in sources.audit if (a.status or "").startswith("denied_"))
    prom_ok = sum(1 for s in sources.prometheus_samples if s.source == "prometheus")

    summary = (
        f"{len(sources.events)} K8s events ({warn_count} Warning, {info_count} Normal), "
        f"{prom_ok}/{len(sources.prometheus_samples)} Prometheus samples collected, "
        f"{sources.logs.total} log entries queried "
        f"({sources.logs.source}), "
        f"{len(sources.audit)} audit rows in window ({denials} denials)."
    )

    timeline_lines = [
        _format_event_line(
            e.timestamp, e.type, e.reason, e.message, e.involved_kind, e.involved_name
        )
        for e in sources.events[:25]
    ]
    timeline = "\n".join(timeline_lines) if timeline_lines else "No events in window."

    header = workload or "cluster"
    return (
        f"# Postmortem — {header}  ({start.isoformat()})\n\n"
        f"**Window:** {start.isoformat()} → {end.isoformat()} ({minutes} min)\n"
        f"**Scope:** {scope}\n\n"
        f"## Summary (deterministic)\n{summary}\n\n"
        f"## Timeline (K8s events, newest first)\n{timeline}\n\n"
        f"## Impact (Prometheus)\n{_format_prometheus(sources)}\n\n"
        f"## Logs (OpenSearch)\n{_format_logs(sources)}\n\n"
        f"## Audit trail (secure-ops)\n{_format_audit(sources)}\n\n"
        f"## Action Items\n- [ ] (fallback mode — LLM narrator disabled; "
        f"verify signals above and fill in)\n"
    )


async def render_postmortem_markdown(
    *,
    llm: UtilityLLM,
    start: datetime,
    end: datetime,
    minutes: int,
    namespace: str | None,
    workload: str | None,
    sources: PostmortemSources,
) -> tuple[str, bool]:
    """Return (markdown, llm_narrated)."""
    fallback = render_markdown_fallback(
        start=start,
        end=end,
        minutes=minutes,
        namespace=namespace,
        workload=workload,
        sources=sources,
    )
    prompt = (
        "You are a senior SRE drafting a Google-SRE-style postmortem. Use Markdown with "
        "these sections in this order: Summary, Timeline, Impact, Root Cause, Action Items. "
        "Summary: 2-3 sentences. Timeline: bullet list, newest first. Impact: bullet list "
        "with concrete numbers. Root Cause: your best hypothesis from the signals. "
        "Action Items: 3-5 specific [ ] todos. Keep it under 400 words. Do not invent "
        "facts beyond the structured context provided."
    )
    structured = {
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "minutes": minutes,
        },
        "scope": {"namespace": namespace, "workload": workload},
        "sources": sources.model_dump(mode="json"),
    }
    llm_text = await llm.narrate(prompt, structured)
    if llm_text:
        return llm_text, True
    return fallback, False
