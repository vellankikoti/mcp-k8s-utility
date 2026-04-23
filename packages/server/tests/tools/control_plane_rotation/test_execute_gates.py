"""Tests for the safety gates in execute_control_plane_rotation."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock


def _make_core_v1(
    *,
    master_names: list[str] | None = None,
    masters_ready: bool = True,
    rotator_pods_active: bool = False,
) -> MagicMock:
    """Build a minimal core_v1 mock for gate tests."""
    core = MagicMock()

    # list_node — used by _cluster_healthy
    if master_names is None:
        master_names = ["master-0"]

    def _make_node(name: str, ready: bool) -> MagicMock:
        cond = MagicMock()
        cond.type = "Ready"
        cond.status = "True" if ready else "False"
        node = MagicMock()
        node.metadata.name = name
        node.status.conditions = [cond]
        return node

    node_list = MagicMock()
    node_list.items = [_make_node(n, masters_ready) for n in master_names]
    core.list_node = AsyncMock(return_value=node_list)

    # list_namespaced_pod — used by _concurrent_rotation
    pod_list = MagicMock()
    if rotator_pods_active:
        active_pod = MagicMock()
        active_pod.status.phase = "Running"
        pod_list.items = [active_pod]
    else:
        pod_list.items = []
    core.list_namespaced_pod = AsyncMock(return_value=pod_list)

    return core


def _business_hours_moment() -> datetime:
    """Wednesday 14:00 UTC — within business-hours window."""
    return datetime(2026, 4, 22, 14, 0, tzinfo=UTC)  # Wednesday


def _off_hours_moment() -> datetime:
    """Saturday 03:00 UTC — outside business-hours window."""
    return datetime(2026, 4, 25, 3, 0, tzinfo=UTC)  # Saturday


async def test_refused_business_hours() -> None:
    from utility_server.tools.control_plane_rotation.execute import (
        execute_control_plane_rotation,
    )

    core = _make_core_v1()
    result = await execute_control_plane_rotation(
        core_v1=core,
        kubeconfig="/fake/kubeconfig",
        node="master-0",
        dry_run=False,
        force_during_business_hours=False,
        now=_business_hours_moment(),
    )
    assert result.status == "refused_business_hours"
    assert result.refusal_reason is not None
    assert "business hours" in result.refusal_reason.lower()
    assert result.step_results == []
    # No Kubernetes mutations should have been called
    core.create_namespaced_pod.assert_not_called()


async def test_business_hours_with_force_proceeds_to_health_check() -> None:
    """With force=True during business hours we pass the BH gate and reach the health gate."""
    from utility_server.tools.control_plane_rotation.execute import (
        execute_control_plane_rotation,
    )

    # One master not-ready so we stop at health gate
    core = _make_core_v1(masters_ready=False)
    result = await execute_control_plane_rotation(
        core_v1=core,
        kubeconfig="/fake/kubeconfig",
        node="master-0",
        dry_run=False,
        force_during_business_hours=True,
        now=_business_hours_moment(),
    )
    assert result.status == "refused_cluster_unhealthy"


async def test_refused_cluster_unhealthy() -> None:
    from utility_server.tools.control_plane_rotation.execute import (
        execute_control_plane_rotation,
    )

    core = _make_core_v1(masters_ready=False)
    result = await execute_control_plane_rotation(
        core_v1=core,
        kubeconfig="/fake/kubeconfig",
        node="master-0",
        dry_run=False,
        now=_off_hours_moment(),
    )
    assert result.status == "refused_cluster_unhealthy"
    assert result.refusal_reason is not None
    assert "not Ready" in result.refusal_reason or "unhealthy" in result.refusal_reason.lower()
    assert result.step_results == []
    core.create_namespaced_pod.assert_not_called()


async def test_refused_concurrent_rotation() -> None:
    from utility_server.tools.control_plane_rotation.execute import (
        execute_control_plane_rotation,
    )

    core = _make_core_v1(rotator_pods_active=True)
    result = await execute_control_plane_rotation(
        core_v1=core,
        kubeconfig="/fake/kubeconfig",
        node="master-0",
        dry_run=False,
        now=_off_hours_moment(),
    )
    assert result.status == "refused_concurrent_rotation"
    assert result.refusal_reason is not None
    assert result.step_results == []
    core.create_namespaced_pod.assert_not_called()


async def test_dry_run_returns_fourteen_skipped_steps() -> None:
    from utility_server.tools.control_plane_rotation.execute import (
        execute_control_plane_rotation,
    )

    # dry_run=True bypasses all real gates; core_v1 is never called for health/concurrency
    core = _make_core_v1()
    result = await execute_control_plane_rotation(
        core_v1=core,
        kubeconfig="/fake/kubeconfig",
        node="master-0",
        dry_run=True,
        now=_off_hours_moment(),
    )
    assert result.status == "planned_dry_run"
    assert result.dry_run is True
    assert len(result.step_results) == 14
    assert all(sr.status == "skipped_dry_run" for sr in result.step_results)
    assert all(sr.exit_code is None for sr in result.step_results)
    assert all(sr.duration_ms is None for sr in result.step_results)
    # Pod must NOT have been created for a dry run
    core.create_namespaced_pod.assert_not_called()


async def test_dry_run_step_indexes_correct() -> None:
    from utility_server.tools.control_plane_rotation.execute import (
        execute_control_plane_rotation,
    )

    core = _make_core_v1()
    result = await execute_control_plane_rotation(
        core_v1=core,
        kubeconfig="/fake/kubeconfig",
        node="master-0",
        dry_run=True,
    )
    indexes = [sr.step.index for sr in result.step_results]
    assert indexes == list(range(1, 15))
