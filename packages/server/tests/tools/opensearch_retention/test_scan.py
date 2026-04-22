from __future__ import annotations

from datetime import UTC, datetime, timedelta

from utility_server.opensearch_client import OpenSearchClient
from utility_server.tools.opensearch_retention.scan import list_old_indices


def _iso(days_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def _stub_client(cat_rows: list[dict], settings_map: dict[str, dict]) -> OpenSearchClient:
    class _Stub(OpenSearchClient):
        def __init__(self) -> None:
            super().__init__(base_url="http://stub")

        async def list_indices(self):  # type: ignore[override]
            return cat_rows

        async def get_index_settings(self, index):  # type: ignore[override]
            return settings_map.get(index, {})

    return _Stub()


async def test_list_old_indices_filters_by_age_and_pattern():
    rows = [
        {
            "index": "logs-2026.03.01",
            "docs.count": "10000",
            "store.size": "52428800",
            "creation.date.string": _iso(60),
        },
        {
            "index": "logs-2026.04.21",
            "docs.count": "20000",
            "store.size": "10485760",
            "creation.date.string": _iso(1),
        },
        {
            "index": ".kibana_1",
            "docs.count": "100",
            "store.size": "1024",
            "creation.date.string": _iso(200),
        },
    ]
    client = _stub_client(rows, settings_map={})
    out = await list_old_indices(client=client, older_than_days=30, index_patterns=["logs-*"])
    assert [i.name for i in out] == ["logs-2026.03.01"]
    # .kibana_1 is older but doesn't match pattern.


async def test_list_old_indices_empty_patterns_returns_empty():
    client = _stub_client([], settings_map={})
    out = await list_old_indices(client=client, older_than_days=30, index_patterns=[])
    assert out == []


async def test_list_old_indices_flags_retention_tag():
    rows = [
        {
            "index": "logs-2026.03.01",
            "docs.count": "10000",
            "store.size": "52428800",
            "creation.date.string": _iso(60),
        }
    ]
    settings = {
        "logs-2026.03.01": {
            "logs-2026.03.01": {"settings": {"index": {"meta": {"retention": "2y-compliance"}}}}
        }
    }
    client = _stub_client(rows, settings_map=settings)
    out = await list_old_indices(client=client, older_than_days=30, index_patterns=["logs-*"])
    assert len(out) == 1
    assert out[0].retention_tagged is True
    assert out[0].matched_pattern == "logs-*"
