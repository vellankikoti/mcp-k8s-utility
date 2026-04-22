from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from utility_server.models import (
    CleanupOutcome,
    CleanupPlan,
    CleanupResult,
)


async def execute_cleanup_plan(
    *,
    core_v1: Any,
    plan: CleanupPlan,
    dry_run: bool = True,
    now: datetime | None = None,
) -> CleanupResult:
    """Delete pods marked will_delete=True in the plan.

    dry_run=True means even approved candidates produce status=skipped_dry_run.
    """
    moment = now or datetime.now(UTC)
    outcomes: list[CleanupOutcome] = []
    deleted = 0
    skipped = 0
    failed = 0

    for candidate in plan.candidates:
        if not candidate.will_delete:
            outcomes.append(
                CleanupOutcome(
                    pod=candidate.pod.ref,
                    status="skipped_policy",
                    error=candidate.skip_reason,
                )
            )
            skipped += 1
            continue
        if dry_run:
            outcomes.append(CleanupOutcome(pod=candidate.pod.ref, status="skipped_dry_run"))
            skipped += 1
            continue
        try:
            await core_v1.delete_namespaced_pod(
                name=candidate.pod.ref.name,
                namespace=candidate.pod.ref.namespace,
            )
            outcomes.append(CleanupOutcome(pod=candidate.pod.ref, status="deleted"))
            deleted += 1
        except Exception as e:
            outcomes.append(CleanupOutcome(pod=candidate.pod.ref, status="failed", error=repr(e)))
            failed += 1

    return CleanupResult(
        dry_run=dry_run,
        executed_at=moment,
        outcomes=outcomes,
        deleted_count=deleted,
        skipped_count=skipped,
        failed_count=failed,
    )
