from __future__ import annotations

from utility_server.prom_client import PromClient
from utility_server.tools.tune_alert_thresholds.analyze import list_noisy_alerts


def _prom_stub(*, first: list, label_lookups: dict[str, list]) -> PromClient:
    class _P(PromClient):
        def __init__(self) -> None:
            super().__init__(base_url="http://stub")
            self._first = first
            self._labels = dict(label_lookups)

        async def instant(self, expr: str):  # type: ignore[override]
            if "count_over_time(ALERTS" in expr:
                return self._first
            for name, payload in self._labels.items():
                if f'alertname="{name}"' in expr:
                    return payload
            return []

    return _P()


async def test_list_noisy_alerts_filters_by_threshold():
    first = [
        {"metric": {"alertname": "KubePodCrashLooping", "severity": "warning"}, "value": [0, "48"]},
        {"metric": {"alertname": "HighCPU", "severity": "warning"}, "value": [0, "4"]},
        {"metric": {"alertname": "Ignored", "severity": "info"}, "value": [0, "0"]},
    ]
    prom = _prom_stub(
        first=first,
        label_lookups={
            "KubePodCrashLooping": [
                {
                    "metric": {
                        "alertname": "KubePodCrashLooping",
                        "severity": "warning",
                        "namespace": "prod",
                    },
                    "value": [0, "1"],
                }
            ],
            "HighCPU": [
                {
                    "metric": {"alertname": "HighCPU", "severity": "warning"},
                    "value": [0, "1"],
                }
            ],
        },
    )
    out = await list_noisy_alerts(prom=prom, window_hours=24.0, min_flaps_per_hour=0.5)
    names = [a.alertname for a in out]
    assert names[0] == "KubePodCrashLooping"
    # min_flaps_per_hour=0.5 over 24h → 12 minimum fires; HighCPU=4 does not qualify.
    assert "HighCPU" not in names
    assert "Ignored" not in names
    assert out[0].fires_count == 48


async def test_list_noisy_alerts_empty_returns_empty_list():
    prom = _prom_stub(first=[], label_lookups={})
    out = await list_noisy_alerts(prom=prom, window_hours=24.0, min_flaps_per_hour=0.5)
    assert out == []


async def test_list_noisy_alerts_surfaces_namespace_label():
    prom = _prom_stub(
        first=[{"metric": {"alertname": "X", "severity": "warning"}, "value": [0, "24"]}],
        label_lookups={
            "X": [
                {
                    "metric": {
                        "alertname": "X",
                        "severity": "warning",
                        "namespace": "payments",
                    },
                    "value": [0, "1"],
                }
            ],
        },
    )
    out = await list_noisy_alerts(prom=prom, window_hours=24.0, min_flaps_per_hour=0.5)
    assert out[0].namespace == "payments"
    assert out[0].severity == "warning"
