from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from utility_server.models import (
    CleanupCandidate,
    CleanupPlan,
    EvictedPodSummary,
    K8sObjectRef,
)
from utility_server.tools.cleanup_evicted_pods.execute import execute_cleanup_plan


def _candidate(name: str, will_delete: bool, skip_reason: str | None = None) -> CleanupCandidate:
    return CleanupCandidate(
        pod=EvictedPodSummary(
            ref=K8sObjectRef(
                kind="Pod",
                api_version="v1",
                namespace="prod",
                name=name,
                uid=f"u-{name}",
            ),
            eviction_reason="Evicted",
            eviction_message="DiskPressure",
            evicted_at=datetime.now(UTC),
            age_hours=3.0,
            node_name="node-1",
            owner_kind="Deployment",
            owner_name="checkout",
        ),
        will_delete=will_delete,
        skip_reason=skip_reason,
    )


def _plan(candidates: list[CleanupCandidate]) -> CleanupPlan:
    return CleanupPlan(
        namespace=None,
        min_age_hours=1.0,
        max_deletes_per_namespace=20,
        namespace_allowlist=[],
        candidates=candidates,
        proposed_at=datetime.now(UTC),
    )


async def test_dry_run_does_not_delete() -> None:
    core = MagicMock()
    core.delete_namespaced_pod = AsyncMock()
    plan = _plan([_candidate("pod-a", True), _candidate("pod-b", True)])
    result = await execute_cleanup_plan(core_v1=core, plan=plan, dry_run=True)
    assert result.dry_run is True
    assert result.deleted_count == 0
    assert result.skipped_count == 2
    assert all(o.status == "skipped_dry_run" for o in result.outcomes)
    core.delete_namespaced_pod.assert_not_awaited()


async def test_real_run_deletes_approved_and_skips_rejected() -> None:
    core = MagicMock()
    core.delete_namespaced_pod = AsyncMock()
    plan = _plan(
        [
            _candidate("pod-a", True),
            _candidate("pod-b", False, "namespace not in allowlist"),
            _candidate("pod-c", True),
        ]
    )
    result = await execute_cleanup_plan(core_v1=core, plan=plan, dry_run=False)
    assert result.deleted_count == 2
    assert result.skipped_count == 1
    assert {o.pod.name for o in result.outcomes if o.status == "deleted"} == {
        "pod-a",
        "pod-c",
    }
    assert core.delete_namespaced_pod.await_count == 2


async def test_real_run_records_failed_delete_without_halting() -> None:
    core = MagicMock()
    core.delete_namespaced_pod = AsyncMock(side_effect=[None, RuntimeError("boom"), None])
    plan = _plan([_candidate(f"p{i}", True) for i in range(3)])
    result = await execute_cleanup_plan(core_v1=core, plan=plan, dry_run=False)
    assert result.deleted_count == 2
    assert result.failed_count == 1
    statuses = [o.status for o in result.outcomes]
    assert statuses.count("deleted") == 2
    assert statuses.count("failed") == 1
