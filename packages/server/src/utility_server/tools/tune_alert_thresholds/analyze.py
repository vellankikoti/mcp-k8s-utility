from __future__ import annotations

from typing import Any

from utility_server.models import NoisyAlert
from utility_server.prom_client import PromClient

_DEFAULT_WINDOW_HOURS = 24.0
_MIN_FLAPS_PER_HOUR = 0.5


def _flaps_query(window_hours: float) -> str:
    return (
        f"sum by (alertname, severity, namespace) "
        f'(changes(ALERTS{{alertstate="firing"}}[{int(window_hours)}h]))'
    )


def _labels_query(alertname: str) -> str:
    # Pull labels of latest sample for context.
    return f'ALERTS{{alertname="{alertname}"}} == 1'


def _labels_from_result(items: list[dict[str, Any]]) -> dict[str, str]:
    if not items:
        return {}
    metric = items[0].get("metric") or {}
    return {k: str(v) for k, v in metric.items() if k not in {"__name__"}}


async def list_noisy_alerts(
    *,
    prom: PromClient,
    window_hours: float = _DEFAULT_WINDOW_HOURS,
    min_flaps_per_hour: float = _MIN_FLAPS_PER_HOUR,
) -> list[NoisyAlert]:
    """Query Prometheus for alerts that flapped often in the window."""
    result = await prom.instant(_flaps_query(window_hours))
    out: list[NoisyAlert] = []
    for entry in result:
        metric = entry.get("metric") or {}
        fires_value = prom.first_value([entry])
        fires = int(fires_value)
        if fires <= 0:
            continue
        flaps_per_hour = fires / window_hours if window_hours > 0 else 0.0
        if flaps_per_hour < min_flaps_per_hour:
            continue
        alertname = str(metric.get("alertname") or "")
        if not alertname:
            continue
        label_result = await prom.instant(_labels_query(alertname))
        labels = _labels_from_result(label_result)
        out.append(
            NoisyAlert(
                alertname=alertname,
                severity=labels.get("severity") or str(metric.get("severity") or "") or None,
                namespace=labels.get("namespace") or str(metric.get("namespace") or "") or None,
                fires_count=fires,
                window_hours=window_hours,
                flaps_per_hour=round(flaps_per_hour, 3),
                labels=labels,
            )
        )
    out.sort(key=lambda a: a.fires_count, reverse=True)
    return out
