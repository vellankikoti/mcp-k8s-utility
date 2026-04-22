from __future__ import annotations

from utility_server.llm.adapter import Provider, UtilityLLM
from utility_server.models import NoisyAlert
from utility_server.tools.tune_alert_thresholds.propose import (
    _recommended_for,
    propose_alert_tuning,
)


def _alert(severity: str = "warning", fires: int = 48) -> NoisyAlert:
    return NoisyAlert(
        alertname="KubePodCrashLooping",
        severity=severity,
        namespace="prod",
        fires_count=fires,
        window_hours=24.0,
        flaps_per_hour=fires / 24.0,
        labels={"alertname": "KubePodCrashLooping", "severity": severity},
    )


def test_recommended_for_flooring():
    # Very high flap rate → minimum 5m floor
    assert _recommended_for(30.0) == "5m"
    # Moderate: 2 flaps/hr → 60m → 1h
    assert _recommended_for(2.0) == "1h"
    # Low: 0.5 flaps/hr → 240m → 4h
    assert _recommended_for(0.5) == "4h"
    # Zero: fallback
    assert _recommended_for(0) == "15m"


async def test_propose_alert_tuning_flags_critical_for_human_review():
    alert = _alert(severity="critical")
    report = await propose_alert_tuning(
        alerts=[alert],
        llm=UtilityLLM(Provider.DISABLED),
        window_hours=24.0,
        min_flaps_per_hour=0.5,
    )
    assert len(report.findings) == 1
    assert report.findings[0].requires_human_review is True
    assert report.findings[0].fallback_only is True  # LLM disabled → fallback_only
    assert report.narration is not None
    assert "1 noisy alert" in report.narration


async def test_propose_alert_tuning_empty_findings_produces_clean_summary():
    report = await propose_alert_tuning(
        alerts=[],
        llm=UtilityLLM(Provider.DISABLED),
        window_hours=24.0,
        min_flaps_per_hour=0.5,
    )
    assert report.findings == []
    assert report.narration is not None
    assert "No noisy alerts" in report.narration


async def test_propose_alert_tuning_non_critical_not_flagged():
    alert = _alert(severity="warning")
    report = await propose_alert_tuning(
        alerts=[alert],
        llm=UtilityLLM(Provider.DISABLED),
        window_hours=24.0,
        min_flaps_per_hour=0.5,
    )
    assert report.findings[0].requires_human_review is False
