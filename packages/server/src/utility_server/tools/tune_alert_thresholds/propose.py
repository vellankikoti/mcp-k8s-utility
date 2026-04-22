from __future__ import annotations

from datetime import UTC, datetime

from utility_server.llm.adapter import UtilityLLM
from utility_server.models import AlertTuningProposal, AlertTuningReport, NoisyAlert


def _recommended_for(flaps_per_hour: float) -> str:
    """Heuristic: set `for:` to twice the mean inter-flap interval, floored at 5m."""
    if flaps_per_hour <= 0:
        return "15m"
    mean_interval_min = 60.0 / flaps_per_hour
    recommended_min = max(5.0, mean_interval_min * 2)
    if recommended_min >= 60:
        return f"{round(recommended_min / 60)}h"
    return f"{round(recommended_min)}m"


def _rationale(alert: NoisyAlert, recommended: str) -> str:
    severity_note = (
        " (critical severity — proposal requires human review before applying)"
        if (alert.severity or "").lower() == "critical"
        else ""
    )
    return (
        f"{alert.alertname} fired {alert.fires_count} times over the last "
        f"{alert.window_hours:.0f}h ({alert.flaps_per_hour:.2f}/hr). "
        f"Recommended `for:` duration: {recommended} to suppress transient flaps"
        f"{severity_note}."
    )


def _deterministic_summary(report_findings: list[AlertTuningProposal], window: float) -> str:
    if not report_findings:
        return f"No noisy alerts found in the last {window:.0f}h."
    n_crit = sum(1 for f in report_findings if f.requires_human_review)
    total = len(report_findings)
    return (
        f"Found {total} noisy alert(s) over {window:.0f}h "
        f"({n_crit} require human review before tuning)."
    )


def _build_proposals(alerts: list[NoisyAlert]) -> list[AlertTuningProposal]:
    out: list[AlertTuningProposal] = []
    for alert in alerts:
        rec = _recommended_for(alert.flaps_per_hour)
        out.append(
            AlertTuningProposal(
                alert=alert,
                current_for=None,
                recommended_for=rec,
                rationale=_rationale(alert, rec),
                requires_human_review=(alert.severity or "").lower() == "critical",
                fallback_only=True,
            )
        )
    return out


async def propose_alert_tuning(
    *,
    alerts: list[NoisyAlert],
    llm: UtilityLLM,
    window_hours: float,
    min_flaps_per_hour: float,
) -> AlertTuningReport:
    findings = _build_proposals(alerts)
    narration_fallback = _deterministic_summary(findings, window_hours)
    structured = {
        "window_hours": window_hours,
        "findings": [f.model_dump(mode="json") for f in findings],
    }
    narration = await llm.narrate(
        "You are an SRE summarising noisy-alert findings for a platform team in 2-3 "
        "sentences. Mention the top 2 alerts by fires_count, and that critical alerts "
        "are flagged for human review before tuning.",
        structured,
    )
    if narration:
        for proposal in findings:
            proposal.fallback_only = False
    return AlertTuningReport(
        window_hours=window_hours,
        min_flaps_per_hour=min_flaps_per_hour,
        findings=findings,
        narration=narration or narration_fallback,
        analyzed_at=datetime.now(UTC),
    )
