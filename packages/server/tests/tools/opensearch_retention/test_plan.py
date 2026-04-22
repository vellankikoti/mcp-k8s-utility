from __future__ import annotations

from datetime import UTC, datetime, timedelta

from utility_server.llm.adapter import Provider, UtilityLLM
from utility_server.models import OpenSearchIndexSummary
from utility_server.opensearch_client import OpenSearchClient
from utility_server.tools.opensearch_retention.plan import (
    _format_bytes,
    propose_retention_plan,
)


def _stub_with_indices(indices: list[OpenSearchIndexSummary]) -> OpenSearchClient:
    class _Stub(OpenSearchClient):
        def __init__(self) -> None:
            super().__init__(base_url="http://stub")

        async def list_indices(self):  # type: ignore[override]
            return [
                {
                    "index": i.name,
                    "docs.count": str(i.doc_count),
                    "store.size": str(i.size_bytes),
                    "creation.date.string": (i.creation_timestamp or datetime.now(UTC))
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
                for i in indices
            ]

        async def get_index_settings(self, index):  # type: ignore[override]
            meta: dict = {}
            match = next((i for i in indices if i.name == index), None)
            if match and match.retention_tagged:
                meta = {index: {"settings": {"index": {"meta": {"retention": "1y"}}}}}
            return meta

    return _Stub()


def _idx(
    name: str,
    age_days: float,
    size_mib: int = 50,
    doc_count: int = 1000,
    retention_tagged: bool = False,
) -> OpenSearchIndexSummary:
    return OpenSearchIndexSummary(
        name=name,
        doc_count=doc_count,
        size_bytes=size_mib * 1024 * 1024,
        creation_timestamp=datetime.now(UTC) - timedelta(days=age_days),
        age_days=age_days,
        retention_tagged=retention_tagged,
        matched_pattern="logs-*",
    )


def test_format_bytes_scales_units():
    assert _format_bytes(512) == "512 B"
    assert _format_bytes(2 * 1024) == "2.0 KiB"
    assert _format_bytes(5 * 1024 * 1024) == "5.0 MiB"


async def test_propose_plan_separates_approved_from_retention_tagged():
    indices = [
        _idx("logs-a", 60),
        _idx("logs-b", 60, retention_tagged=True),
        _idx("logs-c", 60),
    ]
    client = _stub_with_indices(indices)
    llm = UtilityLLM(Provider.DISABLED)
    plan = await propose_retention_plan(
        client=client,
        older_than_days=30,
        index_patterns=["logs-*"],
        max_deletes=50,
        llm=llm,
    )
    approved = [c for c in plan.candidates if c.will_delete]
    skipped = [c for c in plan.candidates if not c.will_delete]
    assert {c.index.name for c in approved} == {"logs-a", "logs-c"}
    assert {c.index.name for c in skipped} == {"logs-b"}
    assert "retention" in (skipped[0].skip_reason or "")


async def test_propose_plan_enforces_rate_limit():
    indices = [_idx(f"logs-{i}", 60) for i in range(10)]
    client = _stub_with_indices(indices)
    plan = await propose_retention_plan(
        client=client,
        older_than_days=30,
        index_patterns=["logs-*"],
        max_deletes=3,
        llm=UtilityLLM(Provider.DISABLED),
    )
    approved = [c for c in plan.candidates if c.will_delete]
    rejected = [c for c in plan.candidates if not c.will_delete]
    assert len(approved) == 3
    assert all("rate limit" in (c.skip_reason or "") for c in rejected)


async def test_propose_plan_deterministic_narration_when_llm_disabled():
    plan = await propose_retention_plan(
        client=_stub_with_indices([_idx("logs-a", 60)]),
        older_than_days=30,
        index_patterns=["logs-*"],
        max_deletes=50,
        llm=UtilityLLM(Provider.DISABLED),
    )
    assert plan.narration and "1 index" in plan.narration


async def test_propose_plan_empty_narration():
    plan = await propose_retention_plan(
        client=_stub_with_indices([]),
        older_than_days=30,
        index_patterns=["logs-*"],
        max_deletes=50,
        llm=UtilityLLM(Provider.DISABLED),
    )
    assert plan.narration and "No OpenSearch indices eligible" in plan.narration
