"""Unit tests for detect_cluster_type()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


def _make_node(
    labels: dict[str, str] | None = None,
    annotations: dict[str, str] | None = None,
) -> MagicMock:
    node = MagicMock()
    node.metadata.labels = labels or {}
    node.metadata.annotations = annotations or {}
    return node


def _make_core(nodes: list[MagicMock]) -> MagicMock:
    node_list = MagicMock()
    node_list.items = nodes
    core = MagicMock()
    core.list_node = AsyncMock(return_value=node_list)
    return core


async def test_k3s_annotation_returns_k3s() -> None:
    from utility_server.tools.control_plane_rotation.detect import detect_cluster_type

    node = _make_node(
        labels={"node-role.kubernetes.io/control-plane": ""},
        annotations={"k3s.io/node-args": '["server"]'},
    )
    core = _make_core([node])
    result = await detect_cluster_type(core)
    assert result == "k3s"


async def test_k3s_internal_ip_annotation_returns_k3s() -> None:
    from utility_server.tools.control_plane_rotation.detect import detect_cluster_type

    node = _make_node(annotations={"k3s.io/internal-ip": "10.0.0.1"})
    core = _make_core([node])
    result = await detect_cluster_type(core)
    assert result == "k3s"


async def test_eks_managed_by_label_returns_managed() -> None:
    from utility_server.tools.control_plane_rotation.detect import detect_cluster_type

    node = _make_node(labels={"node.kubernetes.io/managed-by": "eks.amazonaws.com"})
    core = _make_core([node])
    result = await detect_cluster_type(core)
    assert result == "managed"


async def test_gke_managed_by_label_returns_managed() -> None:
    from utility_server.tools.control_plane_rotation.detect import detect_cluster_type

    node = _make_node(labels={"node.kubernetes.io/managed-by": "gke"})
    core = _make_core([node])
    result = await detect_cluster_type(core)
    assert result == "managed"


async def test_kubeadm_control_plane_returns_kubeadm() -> None:
    from utility_server.tools.control_plane_rotation.detect import detect_cluster_type

    cp_node = _make_node(labels={"node-role.kubernetes.io/control-plane": ""})
    worker = _make_node(labels={})
    core = _make_core([cp_node, worker])
    result = await detect_cluster_type(core)
    assert result == "kubeadm"


async def test_master_label_also_returns_kubeadm() -> None:
    """Legacy 'master' label (pre-1.24) should also detect as kubeadm."""
    from utility_server.tools.control_plane_rotation.detect import detect_cluster_type

    node = _make_node(labels={"node-role.kubernetes.io/master": ""})
    core = _make_core([node])
    result = await detect_cluster_type(core)
    assert result == "kubeadm"


async def test_empty_node_list_returns_unknown() -> None:
    from utility_server.tools.control_plane_rotation.detect import detect_cluster_type

    core = _make_core([])
    result = await detect_cluster_type(core)
    assert result == "unknown"


async def test_list_node_exception_returns_unknown() -> None:
    from utility_server.tools.control_plane_rotation.detect import detect_cluster_type

    core = MagicMock()
    core.list_node = AsyncMock(side_effect=Exception("connection refused"))
    result = await detect_cluster_type(core)
    assert result == "unknown"


async def test_worker_only_cluster_returns_unknown() -> None:
    """A cluster with no control-plane labels and no k3s/managed markers returns 'unknown'."""
    from utility_server.tools.control_plane_rotation.detect import detect_cluster_type

    worker = _make_node(labels={"kubernetes.io/os": "linux"})
    core = _make_core([worker])
    result = await detect_cluster_type(core)
    assert result == "unknown"


async def test_k3s_detection_precedes_control_plane_label() -> None:
    """k3s annotation wins even if control-plane label is present."""
    from utility_server.tools.control_plane_rotation.detect import detect_cluster_type

    node = _make_node(
        labels={"node-role.kubernetes.io/control-plane": ""},
        annotations={"k3s.io/node-args": "[]"},
    )
    core = _make_core([node])
    result = await detect_cluster_type(core)
    assert result == "k3s"


def test_refusal_messages_not_empty() -> None:
    from utility_server.tools.control_plane_rotation.detect import (
        K3S_REFUSAL_MESSAGE,
        MANAGED_REFUSAL_MESSAGE,
    )

    assert "k3s" in K3S_REFUSAL_MESSAGE.lower() or "k3d" in K3S_REFUSAL_MESSAGE.lower()
    assert "kubeadm" in K3S_REFUSAL_MESSAGE
    assert "managed" in MANAGED_REFUSAL_MESSAGE.lower() or "eks" in MANAGED_REFUSAL_MESSAGE
