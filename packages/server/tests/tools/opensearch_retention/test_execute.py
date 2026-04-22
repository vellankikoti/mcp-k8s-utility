from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from utility_server.models import (
    OpenSearchIndexSummary,
    RetentionCleanupCandidate,
    RetentionCleanupPlan,
)
from utility_server.opensearch_client import OpenSearchClient
from utility_server.tools.opensearch_retention.execute import execute_retention_plan


def _candidate(name: str, will_delete: bool, size_mib: int = 50, skip_reason: str | None = None):
    return RetentionCleanupCandidate(
        index=OpenSearchIndexSummary(
            name=name,
            doc_count=1000,
            size_bytes=size_mib * 1024 * 1024,
            creation_timestamp=datetime.now(UTC),
            age_days=60.0,
            retention_tagged=False,
            matched_pattern="logs-*",
        ),
        will_delete=will_delete,
        skip_reason=skip_reason,
    )


def _plan(candidates, total_bytes=0, total_docs=0):
    return RetentionCleanupPlan(
        older_than_days=30,
        index_patterns=["logs-*"],
        max_deletes=50,
        candidates=candidates,
        total_bytes_to_reclaim=total_bytes,
        total_docs_to_remove=total_docs,
        narration="stub",
        proposed_at=datetime.now(UTC),
    )


async def test_dry_run_deletes_nothing():
    client = OpenSearchClient(base_url="http://stub")
    client.delete_index = AsyncMock(return_value=True)  # type: ignore[method-assign]
    plan = _plan([_candidate("logs-a", True), _candidate("logs-b", True)])
    result = await execute_retention_plan(client=client, plan=plan, dry_run=True)
    assert result.dry_run is True
    assert result.deleted_count == 0
    assert result.skipped_count == 2
    assert all(o.status == "skipped_dry_run" for o in result.outcomes)
    client.delete_index.assert_not_awaited()


async def test_real_run_deletes_and_accumulates_bytes():
    client = OpenSearchClient(base_url="http://stub")
    client.delete_index = AsyncMock(return_value=True)  # type: ignore[method-assign]
    plan = _plan(
        [
            _candidate("logs-a", True, size_mib=100),
            _candidate("logs-b", False, size_mib=200, skip_reason="retention tag"),
            _candidate("logs-c", True, size_mib=50),
        ]
    )
    result = await execute_retention_plan(client=client, plan=plan, dry_run=False)
    assert result.deleted_count == 2
    assert result.deleted_bytes == (100 + 50) * 1024 * 1024
    assert result.skipped_count == 1
    assert result.failed_count == 0
    assert client.delete_index.await_count == 2


async def test_real_run_records_failure_and_continues():
    client = OpenSearchClient(base_url="http://stub")
    client.delete_index = AsyncMock(side_effect=[True, False, True])  # type: ignore[method-assign]
    plan = _plan([_candidate(f"logs-{i}", True) for i in range(3)])
    result = await execute_retention_plan(client=client, plan=plan, dry_run=False)
    assert result.deleted_count == 2
    assert result.failed_count == 1
    assert [o.status for o in result.outcomes].count("deleted") == 2
    assert [o.status for o in result.outcomes].count("failed") == 1
