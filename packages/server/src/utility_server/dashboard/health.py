from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


@dataclass
class SystemStatus:
    name: str
    status: str  # "ok" | "unavailable" | "unconfigured"
    detail: str


async def probe_opa() -> SystemStatus:
    url = os.environ.get("SECUREOPS_OPA_URL", "").rstrip("/")
    if not url:
        return SystemStatus("opa", "unconfigured", "SECUREOPS_OPA_URL not set")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{url}/health")
            if r.status_code == 200:
                return SystemStatus("opa", "ok", url)
            return SystemStatus("opa", "unavailable", f"HTTP {r.status_code}")
    except Exception as e:
        return SystemStatus("opa", "unavailable", type(e).__name__)


async def probe_prometheus() -> SystemStatus:
    url = os.environ.get("PROMETHEUS_URL", "").rstrip("/")
    if not url:
        return SystemStatus("prometheus", "unconfigured", "PROMETHEUS_URL not set")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{url}/-/healthy")
            if r.status_code == 200:
                return SystemStatus("prometheus", "ok", url)
            return SystemStatus("prometheus", "unavailable", f"HTTP {r.status_code}")
    except Exception as e:
        return SystemStatus("prometheus", "unavailable", type(e).__name__)


async def probe_opensearch() -> SystemStatus:
    url = os.environ.get("OPENSEARCH_URL", "").rstrip("/")
    if not url:
        return SystemStatus("opensearch", "unconfigured", "OPENSEARCH_URL not set")
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{url}/_cluster/health")
            if r.status_code == 200:
                return SystemStatus("opensearch", "ok", url)
            return SystemStatus("opensearch", "unavailable", f"HTTP {r.status_code}")
    except Exception as e:
        return SystemStatus("opensearch", "unavailable", type(e).__name__)


async def _probe_kubernetes_inner() -> SystemStatus:
    from kubernetes_asyncio import client as k8s_client
    from kubernetes_asyncio import config as k8s_config

    await k8s_config.load_kube_config()
    api = k8s_client.ApiClient()
    version_api = k8s_client.VersionApi(api)
    info = await version_api.get_code()
    await api.close()
    return SystemStatus("kubernetes", "ok", f"server v{info.git_version}")


async def probe_kubernetes() -> SystemStatus:
    import asyncio

    kubeconfig = os.environ.get("KUBECONFIG") or os.path.expanduser("~/.kube/config")
    if not os.path.exists(kubeconfig):
        return SystemStatus("kubernetes", "unconfigured", "no kubeconfig present")
    try:
        return await asyncio.wait_for(_probe_kubernetes_inner(), timeout=5.0)
    except TimeoutError:
        return SystemStatus("kubernetes", "unavailable", "timeout")
    except Exception as e:
        return SystemStatus("kubernetes", "unavailable", type(e).__name__)


def probe_audit_db() -> SystemStatus:
    path = os.environ.get("SECUREOPS_AUDIT_DB", "")
    if not path:
        return SystemStatus("audit", "unconfigured", "SECUREOPS_AUDIT_DB not set")
    if not os.path.exists(path):
        return SystemStatus("audit", "unavailable", f"file not found: {path}")
    return SystemStatus("audit", "ok", path)


async def probe_all() -> list[SystemStatus]:
    import asyncio

    results = await asyncio.gather(
        probe_opa(),
        probe_prometheus(),
        probe_opensearch(),
        probe_kubernetes(),
        return_exceptions=False,
    )
    return [*results, probe_audit_db()]
