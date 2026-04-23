"""Probe control-plane nodes for certificate expiry and read PEM content."""

from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import UTC, datetime
from typing import Any

from utility_server.models import ControlPlaneCertSummary

# Paths relative to the host root (used via `chroot /host`).
# The probe Pod mounts the host root at /host but debian:12-slim has no openssl,
# so we chroot into /host to use the host's openssl binary.
_CERT_FILES = {
    "apiserver": "/etc/kubernetes/pki/apiserver.crt",
    "apiserver-kubelet-client": "/etc/kubernetes/pki/apiserver-kubelet-client.crt",
    "front-proxy-client": "/etc/kubernetes/pki/front-proxy-client.crt",
    "etcd-server": "/etc/kubernetes/pki/etcd/server.crt",
}

# Transient errors observed when kubelet reloads its serving cert during rotation.
_TRANSIENT_MARKERS = (
    "use of closed network connection",
    "connection refused",
    "unexpected EOF",
    "error dialing backend",
    "connection reset by peer",
    "TLS handshake timeout",
    "i/o timeout",
)


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
    retries: int = 5,
    backoff_start_s: float = 2.0,
) -> tuple[int, str, str]:
    """Run `kubectl exec -n NS POD -- CMD...`. Returns (rc, stdout, stderr).

    Retries on transient connection errors that occur when the kubelet reloads
    its serving certificate mid-rotation (e.g. "use of closed network connection").
    """
    env = {**os.environ, "KUBECONFIG": kubeconfig}
    backoff = backoff_start_s
    last_stderr = ""
    for attempt in range(retries + 1):
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
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError:
            proc.kill()
            last_stderr = "timeout"
            if attempt < retries:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 10.0)
                continue
            return -1, "", "timeout"
        rc = proc.returncode or 0
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        last_stderr = stderr
        transient = any(marker in stderr for marker in _TRANSIENT_MARKERS)
        if rc == 0 or not transient or attempt == retries:
            return rc, stdout, stderr
        await asyncio.sleep(backoff)
        backoff = min(backoff * 1.5, 10.0)
    return -1, "", last_stderr


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
            # Use chroot /host so the host's openssl binary is used (debian:12-slim
            # has no openssl). Paths in _CERT_FILES are relative to the host root.
            rc, stdout, _ = await _exec_via_kubectl(
                kubeconfig,
                "kube-system",
                pod_name,
                ["chroot", "/host", "openssl", "x509", "-enddate", "-noout", "-in", path],
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
        # Use chroot /host so the PEM is definitively sourced from the host root.
        rc, stdout, _ = await _exec_via_kubectl(
            kubeconfig,
            "kube-system",
            pod_name,
            ["chroot", "/host", "cat", "/etc/kubernetes/pki/apiserver.crt"],
            timeout_s=15,
        )
        return stdout if rc == 0 else None
    finally:
        with contextlib.suppress(Exception):
            await core_v1.delete_namespaced_pod(
                name=pod_name, namespace="kube-system", grace_period_seconds=0
            )
