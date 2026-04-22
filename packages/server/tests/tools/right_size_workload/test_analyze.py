from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from utility_server.prom_client import PromClient
from utility_server.tools.right_size_workload.analyze import (
    analyze_deployment,
    propose_right_size_plan,
)


def _container(name: str, req_cpu: str, req_mem: str) -> MagicMock:
    c = MagicMock()
    c.name = name
    c.resources.requests = {"cpu": req_cpu, "memory": req_mem}
    c.resources.limits = {}
    return c


def _deployment(name: str, ns: str, containers: list[MagicMock]) -> MagicMock:
    d = MagicMock()
    d.metadata.name = name
    d.metadata.namespace = ns
    d.metadata.uid = f"u-{name}"
    d.spec.template.metadata.labels = {"app": name}
    d.spec.template.spec.containers = containers
    return d


def _prom_mock(cpu_p95: float, cpu_p99: float, mem_p95_bytes: float, mem_p99_bytes: float):
    class _P(PromClient):
        def __init__(self) -> None:
            super().__init__(base_url="http://stub")
            self._queue = [
                [{"value": [0, str(cpu_p95)]}],
                [{"value": [0, str(cpu_p99)]}],
                [{"value": [0, str(mem_p95_bytes)]}],
                [{"value": [0, str(mem_p99_bytes)]}],
            ]

        async def instant(self, expr: str):  # type: ignore[override]
            return self._queue.pop(0) if self._queue else []

    return _P()


async def test_analyze_deployment_builds_recommendation():
    apps_v1 = MagicMock()
    apps_v1.read_namespaced_deployment = AsyncMock(
        return_value=_deployment("api", "prod", [_container("app", "500m", "256Mi")])
    )
    prom = _prom_mock(
        cpu_p95=0.1,
        cpu_p99=0.15,
        mem_p95_bytes=60 * 1024 * 1024,
        mem_p99_bytes=80 * 1024 * 1024,
    )
    recs = await analyze_deployment(
        prom=prom, apps_v1=apps_v1, namespace="prod", name="api", window_days=7
    )
    assert len(recs) == 1
    r = recs[0]
    assert r.container == "app"
    assert r.current.requests.cpu_cores == 0.5
    assert r.current.requests.memory_mib == 256.0
    # Recommended should be ~p99 * headroom (CPU=1.25, mem=1.2)
    assert abs(r.recommended.requests.cpu_cores - 0.15 * 1.25) < 1e-3
    assert abs(r.recommended.requests.memory_mib - 80 * 1.2) < 1.0
    # savings = current - recommended
    assert r.savings_estimate_cpu_cores > 0
    assert r.savings_estimate_memory_mib > 0


async def test_analyze_deployment_honors_minimum_floors():
    apps_v1 = MagicMock()
    apps_v1.read_namespaced_deployment = AsyncMock(
        return_value=_deployment("api", "prod", [_container("app", "1", "1Gi")])
    )
    prom = _prom_mock(0.0, 0.0, 0.0, 0.0)
    recs = await analyze_deployment(prom=prom, apps_v1=apps_v1, namespace="prod", name="api")
    assert recs[0].recommended.requests.cpu_cores >= 0.01
    assert recs[0].recommended.requests.memory_mib >= 16.0


async def test_propose_plan_iterates_all_deployments():
    a = _deployment("api", "prod", [_container("app", "500m", "256Mi")])
    b = _deployment("worker", "prod", [_container("w", "100m", "128Mi")])
    apps_v1 = MagicMock()
    apps_v1.list_namespaced_deployment = AsyncMock(return_value=MagicMock(items=[a, b]))
    apps_v1.read_namespaced_deployment = AsyncMock(side_effect=[a, b])
    prom = _prom_mock(0.1, 0.15, 50 * 1024 * 1024, 70 * 1024 * 1024)
    # We need 8 prom responses (2 deployments x 4 queries each). Extend queue:
    prom._queue.extend(  # type: ignore[attr-defined]
        [
            [{"value": [0, "0.1"]}],
            [{"value": [0, "0.15"]}],
            [{"value": [0, str(50 * 1024 * 1024)]}],
            [{"value": [0, str(70 * 1024 * 1024)]}],
        ]
    )
    plan = await propose_right_size_plan(
        prom=prom, apps_v1=apps_v1, namespace="prod", window_days=7
    )
    assert plan.namespace == "prod"
    assert {r.ref.name for r in plan.recommendations} == {"api", "worker"}
