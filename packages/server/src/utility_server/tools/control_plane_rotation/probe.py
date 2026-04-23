"""Probe control-plane nodes for certificate expiry and read PEM content."""

from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import UTC, datetime
from typing import Any

from utility_server.models import ControlPlaneCertSummary

_CERT_FILES = {
    "apiserver": "/host/etc/kubernetes/pki/apiserver.crt",
    "apiserver-kubelet-client": "/host/etc/kubernetes/pki/apiserver-kubelet-client.crt",
    "front-proxy-client": "/host/etc/kubernetes/pki/front-proxy-client.crt",
    "etcd-server": "/host/etc/kubernetes/pki/etcd/server.crt",
}


async def list_master_nodes(core_v1: Any) -> list[str]:
    out: list[str] = []
    try:
        nodes = await core_v1.list_node(label_selector="node-role.kubernetes.io/control-plane")
    except Exception:
        return []
    for n in getattr(nodes, "items", None) or []:
        name = getattr(n.metadata, "name", None)
        if name:
            out.append(name)
    return sorted(out)


def _read_only_pod_manifest(node: str, name_suffix: str) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "generateName": f"secureops-cp-probe-{name_suffix}-",
            "namespace": "kube-system",
            "labels": {
                "app.kubernetes.io/name": "mcp-k8s-utility",
                "app.kubernetes.io/component": "cp-cert-probe",
            },
        },
        "spec": {
            "nodeName": node,
            "restartPolicy": "Never",
            "tolerations": [{"operator": "Exists"}],
            "hostPID": False,
            "hostNetwork": False,
            "containers": [
                {
                    "name": "probe",
                    "image": "debian:12-slim",
                    "command": ["sleep", "60"],
                    "securityContext": {"runAsUser": 0, "privileged": True},
                    "volumeMounts": [
                        {"name": "host", "mountPath": "/host", "readOnly": True},
                    ],
                }
            ],
            "volumes": [
                {"name": "host", "hostPath": {"path": "/", "type": "Directory"}},
            ],
        },
    }


async def _wait_running(core_v1: Any, namespace: str, name: str, timeout_s: float) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        try:
            pod = await core_v1.read_namespaced_pod(name=name, namespace=namespace)
        except Exception:
            await asyncio.sleep(1)
            continue
        phase = getattr(pod.status, "phase", "")
        if phase == "Running":
            return True
        if phase in {"Failed", "Succeeded"}:
            return False
        await asyncio.sleep(1)
    return False


async def _exec_via_kubectl(
    kubeconfig: str,
    namespace: str,
    name: str,
    cmd: list[str],
    timeout_s: float = 60.0,
) -> tuple[int, str, str]:
    """Run `kubectl exec -n NS POD -- CMD...`. Returns (rc, stdout, stderr)."""
    env = {**os.environ, "KUBECONFIG": kubeconfig}
    proc = await asyncio.create_subprocess_exec(
        "kubectl",
        "-n",
        namespace,
        "exec",
        name,
        "--",
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        return -1, "", "timeout"
    return (
        proc.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def parse_openssl_enddate(line: str) -> datetime | None:
    """`openssl x509 -enddate -noout` output is `notAfter=Nov  5 12:34:56 2026 GMT`."""
    if "=" not in line:
        return None
    date_str = line.split("=", 1)[1].strip()
    # Try with single space first (some openssl versions), then double space for day < 10
    for fmt in ("%b %d %H:%M:%S %Y %Z", "%b  %d %H:%M:%S %Y %Z"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


async def probe_node_certs(
    *,
    core_v1: Any,
    kubeconfig: str,
    node: str,
    now: datetime | None = None,
) -> ControlPlaneCertSummary:
    moment = now or datetime.now(UTC)
    manifest = _read_only_pod_manifest(node, "probe")
    try:
        created = await core_v1.create_namespaced_pod(namespace="kube-system", body=manifest)
    except Exception:
        return ControlPlaneCertSummary(
            node=node, certs={}, soonest_days_until_expiry=None, source="unavailable"
        )

    pod_name = getattr(created.metadata, "name", "")
    try:
        if not await _wait_running(core_v1, "kube-system", pod_name, timeout_s=60):
            return ControlPlaneCertSummary(
                node=node,
                certs={},
                soonest_days_until_expiry=None,
                source="unavailable",
            )

        certs: dict[str, datetime | None] = {}
        for key, path in _CERT_FILES.items():
            rc, stdout, _ = await _exec_via_kubectl(
                kubeconfig,
                "kube-system",
                pod_name,
                ["openssl", "x509", "-enddate", "-noout", "-in", path],
                timeout_s=15,
            )
            if rc == 0:
                dt = parse_openssl_enddate(stdout.strip())
                certs[key] = dt
            else:
                certs[key] = None

        valid = [d for d in certs.values() if d is not None]
        soonest = int((min(valid) - moment).total_seconds() // 86400) if valid else None
        return ControlPlaneCertSummary(
            node=node,
            certs=certs,
            soonest_days_until_expiry=soonest,
            source="probed",
        )
    finally:
        with contextlib.suppress(Exception):
            await core_v1.delete_namespaced_pod(
                name=pod_name, namespace="kube-system", grace_period_seconds=0
            )


async def check_control_plane_cert_expiry(
    *,
    core_v1: Any,
    kubeconfig: str,
) -> list[ControlPlaneCertSummary]:
    masters = await list_master_nodes(core_v1)
    results: list[ControlPlaneCertSummary] = []
    for node in masters:
        results.append(await probe_node_certs(core_v1=core_v1, kubeconfig=kubeconfig, node=node))
    return results


async def read_apiserver_cert_pem(
    *,
    core_v1: Any,
    kubeconfig: str,
    node: str,
) -> str | None:
    manifest = _read_only_pod_manifest(node, "bundle")
    try:
        created = await core_v1.create_namespaced_pod(namespace="kube-system", body=manifest)
    except Exception:
        return None
    pod_name = getattr(created.metadata, "name", "")
    try:
        if not await _wait_running(core_v1, "kube-system", pod_name, timeout_s=60):
            return None
        rc, stdout, _ = await _exec_via_kubectl(
            kubeconfig,
            "kube-system",
            pod_name,
            ["cat", "/host/etc/kubernetes/pki/apiserver.crt"],
            timeout_s=15,
        )
        return stdout if rc == 0 else None
    finally:
        with contextlib.suppress(Exception):
            await core_v1.delete_namespaced_pod(
                name=pod_name, namespace="kube-system", grace_period_seconds=0
            )
