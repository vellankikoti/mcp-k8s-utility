"""Cluster-type detection for control-plane rotation tools."""

from __future__ import annotations

from typing import Any


async def detect_cluster_type(core_v1: Any) -> str:
    """Return one of: 'kubeadm' | 'k3s' | 'managed' | 'unknown'.

    Heuristics (checked in order):
    - Any node label contains 'node.kubernetes.io/managed-by' with an EKS/GKE/AKS marker
      → 'managed' (cloud-managed control plane; cert rotation is the provider's job).
    - Any node has annotation 'k3s.io/node-args' or 'k3s.io/internal-ip'
      → 'k3s' (k3d/k3s; uses `k3s certificate rotate`, not kubeadm).
    - At least one node has the control-plane role label and no k3s markers
      → 'kubeadm'.
    - Otherwise → 'unknown'.
    """
    try:
        nodes = await core_v1.list_node()
    except Exception:
        return "unknown"

    saw_control_plane = False
    for n in nodes.items:
        labels: dict[str, str] = getattr(n.metadata, "labels", None) or {}
        annotations: dict[str, str] = getattr(n.metadata, "annotations", None) or {}

        managed_by = labels.get("node.kubernetes.io/managed-by", "")
        if managed_by and any(m in managed_by for m in ("eks", "gke", "aks", "managed")):
            return "managed"

        if "k3s.io/node-args" in annotations or "k3s.io/internal-ip" in annotations:
            return "k3s"

        if (
            "node-role.kubernetes.io/control-plane" in labels
            or "node-role.kubernetes.io/master" in labels
        ):
            saw_control_plane = True

    if saw_control_plane:
        return "kubeadm"
    return "unknown"


K3S_REFUSAL_MESSAGE = (
    "This cluster appears to be k3s/k3d. k3s uses its own certificate management "
    "(`k3s certificate rotate`) and stores certs under `/var/lib/rancher/k3s/server/tls/`, "
    "not `/etc/kubernetes/pki/`. mcp-k8s-utility's control-plane rotation tools only "
    "support kubeadm-managed clusters. For k3s, run `k3s certificate rotate --service=*` "
    "on each master node. See: https://docs.k3s.io/cli/certificate"
)

MANAGED_REFUSAL_MESSAGE = (
    "This cluster is managed (EKS/GKE/AKS). Control-plane certificates are managed by "
    "the cloud provider. Use the provider's rotation mechanism instead."
)
