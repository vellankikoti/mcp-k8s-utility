from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from utility_server.tools.cleanup_evicted_pods.scan import list_evicted_pods


def _pod(
    name: str,
    namespace: str,
    phase: str,
    reason: str | None,
    age_hours: float = 2.0,
    node: str = "node-1",
    owner_kind: str = "Deployment",
    owner_name: str = "checkout",
) -> MagicMock:
    p = MagicMock()
    p.metadata.name = name
    p.metadata.namespace = namespace
    p.metadata.uid = f"u-{name}"
    p.metadata.creation_timestamp = datetime.now(UTC) - timedelta(hours=age_hours)
    ref = MagicMock()
    ref.controller = True
    ref.kind = owner_kind
    ref.name = owner_name
    p.metadata.owner_references = [ref]
    p.status.phase = phase
    p.status.reason = reason
    p.status.start_time = datetime.now(UTC) - timedelta(hours=age_hours)
    p.status.message = "The node was low on resource: ephemeral-storage"
    p.spec.node_name = node
    return p


async def test_list_evicted_pods_filters_non_evicted() -> None:
    core = MagicMock()
    core.list_pod_for_all_namespaces = AsyncMock(
        return_value=MagicMock(
            items=[
                _pod("a", "prod", "Failed", "Evicted"),
                _pod("b", "prod", "Failed", "Error"),  # Failed but not Evicted
                _pod("c", "prod", "Running", None),  # Running
            ]
        )
    )
    out = await list_evicted_pods(core, namespace=None)
    assert {p.ref.name for p in out} == {"a"}


async def test_list_evicted_pods_namespaced() -> None:
    core = MagicMock()
    items = [_pod("a", "prod", "Failed", "Evicted")]
    core.list_namespaced_pod = AsyncMock(return_value=MagicMock(items=items))
    core.list_pod_for_all_namespaces = AsyncMock(return_value=MagicMock(items=[]))
    out = await list_evicted_pods(core, namespace="prod")
    assert len(out) == 1
    assert out[0].ref.namespace == "prod"
    core.list_namespaced_pod.assert_awaited_once()
    core.list_pod_for_all_namespaces.assert_not_awaited()


async def test_list_evicted_pods_extracts_owner() -> None:
    core = MagicMock()
    core.list_pod_for_all_namespaces = AsyncMock(
        return_value=MagicMock(
            items=[
                _pod(
                    "a",
                    "prod",
                    "Failed",
                    "Evicted",
                    owner_kind="ReplicaSet",
                    owner_name="checkout-xyz",
                )
            ]
        )
    )
    out = await list_evicted_pods(core)
    assert out[0].owner_kind == "ReplicaSet"
    assert out[0].owner_name == "checkout-xyz"
