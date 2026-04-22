from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from utility_server.tools.cleanup_evicted_pods.plan import propose_cleanup_plan


def _pod(name: str, namespace: str, age_hours: float = 2.0) -> MagicMock:
    p = MagicMock()
    p.metadata.name = name
    p.metadata.namespace = namespace
    p.metadata.uid = f"u-{name}"
    ref = MagicMock()
    ref.controller = True
    ref.kind = "Deployment"
    ref.name = "checkout"
    p.metadata.owner_references = [ref]
    p.metadata.creation_timestamp = datetime.now(UTC) - timedelta(hours=age_hours)
    p.status.phase = "Failed"
    p.status.reason = "Evicted"
    p.status.start_time = datetime.now(UTC) - timedelta(hours=age_hours)
    p.status.message = "DiskPressure"
    p.spec.node_name = "node-1"
    return p


async def test_plan_marks_recent_pods_not_eligible() -> None:
    core = MagicMock()
    core.list_pod_for_all_namespaces = AsyncMock(
        return_value=MagicMock(items=[_pod("too-fresh", "prod", age_hours=0.1)])
    )
    plan = await propose_cleanup_plan(core_v1=core, min_age_hours=1.0)
    assert plan.candidates[0].will_delete is False
    assert "too recent" in (plan.candidates[0].skip_reason or "")


async def test_plan_rate_limits_per_namespace() -> None:
    core = MagicMock()
    items = [_pod(f"pod-{i}", "prod", age_hours=5.0) for i in range(5)]
    core.list_pod_for_all_namespaces = AsyncMock(return_value=MagicMock(items=items))
    plan = await propose_cleanup_plan(core_v1=core, min_age_hours=1.0, max_deletes_per_namespace=2)
    approved = [c for c in plan.candidates if c.will_delete]
    rejected = [c for c in plan.candidates if not c.will_delete]
    assert len(approved) == 2
    assert len(rejected) == 3
    assert all("rate limit" in (c.skip_reason or "") for c in rejected)


async def test_plan_respects_env_allowlist(monkeypatch: object) -> None:
    monkeypatch.setenv("UTILITY_CLEANUP_NAMESPACE_ALLOWLIST", "prod,staging")  # type: ignore[attr-defined]
    core = MagicMock()
    items = [
        _pod("a", "prod", age_hours=5.0),
        _pod("b", "test", age_hours=5.0),
    ]
    core.list_pod_for_all_namespaces = AsyncMock(return_value=MagicMock(items=items))
    plan = await propose_cleanup_plan(core_v1=core, min_age_hours=1.0)
    names = {(c.pod.ref.name, c.will_delete) for c in plan.candidates}
    assert ("a", True) in names
    assert ("b", False) in names


async def test_plan_explicit_allowlist_overrides_env(monkeypatch: object) -> None:
    monkeypatch.setenv("UTILITY_CLEANUP_NAMESPACE_ALLOWLIST", "prod")  # type: ignore[attr-defined]
    core = MagicMock()
    items = [_pod("a", "test", age_hours=5.0)]
    core.list_pod_for_all_namespaces = AsyncMock(return_value=MagicMock(items=items))
    plan = await propose_cleanup_plan(core_v1=core, min_age_hours=1.0, namespace_allowlist=["test"])
    assert plan.candidates[0].will_delete is True
