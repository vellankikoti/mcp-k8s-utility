from __future__ import annotations

from datetime import UTC, datetime

from utility_server.models import (
    RetentionCleanupOutcome,
    RetentionCleanupPlan,
    RetentionCleanupResult,
)
from utility_server.opensearch_client import OpenSearchClient


async def execute_retention_plan(
    *,
    client: OpenSearchClient,
    plan: RetentionCleanupPlan,
    dry_run: bool = True,
    now: datetime | None = None,
) -> RetentionCleanupResult:
    moment = now or datetime.now(UTC)
    outcomes: list[RetentionCleanupOutcome] = []
    deleted_count = 0
    deleted_bytes = 0
    skipped_count = 0
    failed_count = 0

    for candidate in plan.candidates:
        name = candidate.index.name
        size = candidate.index.size_bytes
        if not candidate.will_delete:
            outcomes.append(
                RetentionCleanupOutcome(
                    index=name,
                    status="skipped_policy",
                    size_bytes=size,
                    error=candidate.skip_reason,
                )
            )
            skipped_count += 1
            continue
        if dry_run:
            outcomes.append(
                RetentionCleanupOutcome(index=name, status="skipped_dry_run", size_bytes=size)
            )
            skipped_count += 1
            continue
        ok = await client.delete_index(name)
        if ok:
            outcomes.append(RetentionCleanupOutcome(index=name, status="deleted", size_bytes=size))
            deleted_count += 1
            deleted_bytes += size
        else:
            outcomes.append(
                RetentionCleanupOutcome(
                    index=name,
                    status="failed",
                    size_bytes=size,
                    error="DELETE /{index} returned non-2xx or unreachable",
                )
            )
            failed_count += 1

    return RetentionCleanupResult(
        dry_run=dry_run,
        executed_at=moment,
        outcomes=outcomes,
        deleted_count=deleted_count,
        deleted_bytes=deleted_bytes,
        skipped_count=skipped_count,
        failed_count=failed_count,
    )
