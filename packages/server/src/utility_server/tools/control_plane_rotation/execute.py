"""Execute the control-plane certificate rotation runbook on a single master node.

Safety layers (all checked before real execution):
1. Business-hours gate — reuses ``is_business_hours`` from renew_certificate.
2. Cluster-health pre-check — all masters must be Ready.
3. Concurrency guard — no other rotation Pod may be active.
4. Dry-run default — returns planned steps without touching the cluster.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any

from utility_server.models import (
    ControlPlaneRotationResult,
    RotationStep,
    RotationStepResult,
)
from utility_server.tools.control_plane_rotation.probe import (
    _exec_via_kubectl,
    _wait_running,
)
from utility_server.tools.control_plane_rotation.runbook import ROTATION_COMMANDS
from utility_server.tools.renew_certificate.plan import is_business_hours


async def _cluster_healthy(core_v1: Any) -> tuple[bool, str]:
    try:
        nodes = await core_v1.list_node(label_selector="node-role.kubernetes.io/control-plane")
    except Exception as e:
        return False, f"list_node failed: {e!r}"
    not_ready: list[str] = []
    for n in nodes.items:
        conds = getattr(n.status, "conditions", None) or []
        ready = next((c for c in conds if c.type == "Ready"), None)
        if ready is None or ready.status != "True":
            not_ready.append(n.metadata.name)
    if not_ready:
        return False, f"masters not Ready: {','.join(not_ready)}"
    return True, "all masters Ready"


async def _concurrent_rotation(core_v1: Any) -> bool:
    try:
        pods = await core_v1.list_namespaced_pod(
            namespace="kube-system",
            label_selector="app.kubernetes.io/component=cp-cert-rotator",
        )
    except Exception:
        return False
    for p in pods.items:
        phase = getattr(p.status, "phase", "")
        if phase in ("Pending", "Running"):
            return True
    return False


def _executor_pod(node: str) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "generateName": "secureops-cp-rotation-",
            "namespace": "kube-system",
            "labels": {
                "app.kubernetes.io/name": "mcp-k8s-utility",
                "app.kubernetes.io/component": "cp-cert-rotator",
            },
        },
        "spec": {
            "nodeName": node,
            "restartPolicy": "Never",
            "hostNetwork": True,
            "hostPID": True,
            "hostIPC": True,
            "tolerations": [{"operator": "Exists"}],
            "containers": [
                {
                    "name": "runner",
                    "image": "debian:12-slim",
                    "command": ["sleep", "3600"],
                    "securityContext": {"privileged": True, "runAsUser": 0},
                    "volumeMounts": [{"name": "host", "mountPath": "/host"}],
                }
            ],
            "volumes": [
                {
                    "name": "host",
                    "hostPath": {"path": "/", "type": "Directory"},
                }
            ],
        },
    }


def _chroot(cmd: str) -> list[str]:
    return ["chroot", "/host", "sh", "-c", cmd]


async def execute_control_plane_rotation(
    *,
    core_v1: Any,
    kubeconfig: str,
    node: str,
    dry_run: bool = True,
    force_during_business_hours: bool = False,
    now: datetime | None = None,
) -> ControlPlaneRotationResult:
    moment = now or datetime.now(UTC)
    step_results: list[RotationStepResult] = []

    # --- Gate 1: business hours ---
    if not dry_run and is_business_hours(moment) and not force_during_business_hours:
        return ControlPlaneRotationResult(
            node=node,
            dry_run=False,
            started_at=moment,
            completed_at=moment,
            status="refused_business_hours",
            step_results=[],
            refusal_reason=(
                "Rotation refused during UTC business hours. "
                "Pass force_during_business_hours=True with change-control approval."
            ),
        )

    # --- Gate 2: cluster health ---
    healthy, detail = await _cluster_healthy(core_v1)
    if not dry_run and not healthy:
        return ControlPlaneRotationResult(
            node=node,
            dry_run=False,
            started_at=moment,
            completed_at=moment,
            status="refused_cluster_unhealthy",
            step_results=[],
            refusal_reason=f"Cluster not healthy: {detail}",
        )

    # --- Gate 3: concurrency guard ---
    if not dry_run and await _concurrent_rotation(core_v1):
        return ControlPlaneRotationResult(
            node=node,
            dry_run=False,
            started_at=moment,
            completed_at=moment,
            status="refused_concurrent_rotation",
            step_results=[],
            refusal_reason=("Another control-plane rotation Pod is already active in kube-system."),
        )

    # --- Dry-run: return the step list without executing ---
    if dry_run:
        from utility_server.tools.control_plane_rotation.runbook import generate_runbook

        plan = generate_runbook(node)
        for step in plan.steps:
            step_results.append(
                RotationStepResult(
                    step=step,
                    status="skipped_dry_run",
                    stdout="",
                    stderr="",
                    exit_code=None,
                    duration_ms=None,
                )
            )
        return ControlPlaneRotationResult(
            node=node,
            dry_run=True,
            started_at=moment,
            completed_at=datetime.now(UTC),
            status="planned_dry_run",
            step_results=step_results,
            refusal_reason=None,
        )

    # --- Real execution ---
    pod = await core_v1.create_namespaced_pod(namespace="kube-system", body=_executor_pod(node))
    pod_name = pod.metadata.name
    try:
        if not await _wait_running(core_v1, "kube-system", pod_name, timeout_s=120):
            return ControlPlaneRotationResult(
                node=node,
                dry_run=False,
                started_at=moment,
                completed_at=datetime.now(UTC),
                status="failed_mid_rotation",
                step_results=[],
                refusal_reason="Executor Pod did not reach Running within 120s.",
            )

        failed = False
        last_failed_index = 0
        for i, (command, description) in enumerate(ROTATION_COMMANDS, start=1):
            step = RotationStep(index=i, command=command, description=description)
            t0 = datetime.now(UTC)
            rc, stdout, stderr = await _exec_via_kubectl(
                kubeconfig,
                "kube-system",
                pod_name,
                _chroot(command),
                timeout_s=60,
            )
            duration_ms = int((datetime.now(UTC) - t0).total_seconds() * 1000)
            if rc != 0:
                step_results.append(
                    RotationStepResult(
                        step=step,
                        status="failed",
                        stdout=stdout[-4000:],
                        stderr=stderr[-4000:],
                        exit_code=rc,
                        duration_ms=duration_ms,
                    )
                )
                failed = True
                last_failed_index = i
                break
            step_results.append(
                RotationStepResult(
                    step=step,
                    status="executed",
                    stdout=stdout[-4000:],
                    stderr=stderr[-4000:],
                    exit_code=rc,
                    duration_ms=duration_ms,
                )
            )

        if failed:
            # Best-effort rollback: restore manifests and restart kubelet.
            await _exec_via_kubectl(
                kubeconfig,
                "kube-system",
                pod_name,
                _chroot(
                    "mv /home/certs/*.yaml /etc/kubernetes/manifests/ 2>/dev/null || true;"
                    " systemctl restart kubelet"
                ),
                timeout_s=30,
            )
            return ControlPlaneRotationResult(
                node=node,
                dry_run=False,
                started_at=moment,
                completed_at=datetime.now(UTC),
                status="rolled_back",
                step_results=step_results,
                refusal_reason=(
                    f"Step {last_failed_index} failed; attempted best-effort rollback."
                ),
            )

        return ControlPlaneRotationResult(
            node=node,
            dry_run=False,
            started_at=moment,
            completed_at=datetime.now(UTC),
            status="completed",
            step_results=step_results,
            refusal_reason=None,
        )
    finally:
        with contextlib.suppress(Exception):
            await core_v1.delete_namespaced_pod(
                name=pod_name, namespace="kube-system", grace_period_seconds=0
            )
