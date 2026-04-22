from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from utility_server.models import (
    K8sObjectRef,
    ResourceQuantities,
    ResourceRecommendation,
    RightSizePlan,
    WorkloadResources,
)
from utility_server.prom_client import PromClient

_CPU_HEADROOM = 1.25  # +25% buffer over observed p99
_MEM_HEADROOM = 1.20  # +20% buffer over observed p99
_MIN_CPU_CORES = 0.01  # 10 millicores — k8s minimum sanity
_MIN_MEM_MIB = 16.0


def parse_cpu(value: str | int | float | None) -> float:
    """Kubernetes CPU quantity → cores (float). None / bad → 0.0."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return 0.0
    try:
        if s.endswith("m"):
            return float(s[:-1]) / 1000.0
        if s.endswith("n"):
            return float(s[:-1]) / 1_000_000_000.0
        if s.endswith("u"):
            return float(s[:-1]) / 1_000_000.0
        return float(s)
    except ValueError:
        return 0.0


def parse_memory_mib(value: str | int | float | None) -> float:
    """Kubernetes memory quantity → MiB (float). None / bad → 0.0."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) / (1024 * 1024)
    s = str(value).strip()
    if not s:
        return 0.0
    units = {
        "Ki": 1 / 1024,
        "Mi": 1.0,
        "Gi": 1024.0,
        "Ti": 1024 * 1024,
        "K": 1000 / (1024 * 1024),
        "M": 1_000_000 / (1024 * 1024),
        "G": 1_000_000_000 / (1024 * 1024),
    }
    for suffix, factor in units.items():
        if s.endswith(suffix):
            try:
                return float(s[: -len(suffix)]) * factor
            except ValueError:
                return 0.0
    try:
        return float(s) / (1024 * 1024)
    except ValueError:
        return 0.0


def _extract_current(container: Any) -> WorkloadResources:
    resources = getattr(container, "resources", None)
    requests = getattr(resources, "requests", None) or {}
    limits = getattr(resources, "limits", None) or {}
    req = ResourceQuantities(
        cpu_cores=parse_cpu(requests.get("cpu") if isinstance(requests, dict) else None),
        memory_mib=parse_memory_mib(requests.get("memory") if isinstance(requests, dict) else None),
    )
    lim = None
    if isinstance(limits, dict) and limits:
        lim = ResourceQuantities(
            cpu_cores=parse_cpu(limits.get("cpu")),
            memory_mib=parse_memory_mib(limits.get("memory")),
        )
    return WorkloadResources(requests=req, limits=lim)


def _recommend(
    p95_cpu: float, p99_cpu: float, p95_mem: float, p99_mem: float
) -> ResourceQuantities:
    recommended_cpu = max(_MIN_CPU_CORES, round(p99_cpu * _CPU_HEADROOM, 3))
    recommended_mem = max(_MIN_MEM_MIB, round(p99_mem * _MEM_HEADROOM, 1))
    return ResourceQuantities(cpu_cores=recommended_cpu, memory_mib=recommended_mem)


def _rationale(
    current: WorkloadResources,
    p95: ResourceQuantities,
    p99: ResourceQuantities,
    recommended: ResourceQuantities,
) -> str:
    return (
        f"Over a 7d window the container used p95={p95.cpu_cores:.3f} cores / "
        f"{p95.memory_mib:.0f} MiB and p99={p99.cpu_cores:.3f} cores / "
        f"{p99.memory_mib:.0f} MiB. Currently requests "
        f"{current.requests.cpu_cores:.3f} cores / {current.requests.memory_mib:.0f} MiB. "
        f"Recommended requests: {recommended.cpu_cores:.3f} cores / "
        f"{recommended.memory_mib:.0f} MiB (p99 + headroom)."
    )


def _cpu_q_for_promql(rate_window: str = "5m") -> str:
    return f"rate(container_cpu_usage_seconds_total{{{{workload_selector}}}}[{rate_window}])"


def _mem_q_for_promql() -> str:
    return "container_memory_working_set_bytes{{{workload_selector}}}"


async def analyze_deployment(
    *,
    prom: PromClient,
    apps_v1: Any,
    namespace: str,
    name: str,
    window_days: int = 7,
) -> list[ResourceRecommendation]:
    dep = await apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
    pod_labels = dict(getattr(dep.spec.template.metadata, "labels", None) or {})
    selector = ",".join(f'{k}="{v}"' for k, v in sorted(pod_labels.items()))
    if not selector:
        selector = f'namespace="{namespace}"'
    workload_filter = f'namespace="{namespace}",pod=~".*"'  # broad fallback
    _ = selector  # reserved for future label-based selection

    recommendations: list[ResourceRecommendation] = []
    containers = getattr(dep.spec.template.spec, "containers", None) or []
    for container in containers:
        cname = getattr(container, "name", "") or ""
        current = _extract_current(container)

        # Prometheus queries. Use container label to scope.
        container_filter = f'{workload_filter},container="{cname}",image!=""'
        # p99 CPU cores over the window (instantaneous quantile_over_time on rate)
        cpu_p95_expr = (
            f"quantile_over_time(0.95, "
            f"sum by (pod) (rate(container_cpu_usage_seconds_total{{{container_filter}}}[5m]))"
            f"[{window_days}d:5m])"
        )
        cpu_p99_expr = cpu_p95_expr.replace("quantile_over_time(0.95,", "quantile_over_time(0.99,")
        mem_p95_expr = (
            f"quantile_over_time(0.95, "
            f"sum by (pod) (container_memory_working_set_bytes{{{container_filter}}})"
            f"[{window_days}d:5m])"
        )
        mem_p99_expr = mem_p95_expr.replace("quantile_over_time(0.95,", "quantile_over_time(0.99,")

        p95_cpu = prom.first_value(await prom.instant(cpu_p95_expr))
        p99_cpu = prom.first_value(await prom.instant(cpu_p99_expr))
        p95_mem_bytes = prom.first_value(await prom.instant(mem_p95_expr))
        p99_mem_bytes = prom.first_value(await prom.instant(mem_p99_expr))
        p95_mem = p95_mem_bytes / (1024 * 1024)
        p99_mem = p99_mem_bytes / (1024 * 1024)

        observed_p95 = ResourceQuantities(cpu_cores=p95_cpu, memory_mib=p95_mem)
        observed_p99 = ResourceQuantities(cpu_cores=p99_cpu, memory_mib=p99_mem)
        rec_req = _recommend(p95_cpu, p99_cpu, p95_mem, p99_mem)
        recommended = WorkloadResources(requests=rec_req, limits=None)

        recommendations.append(
            ResourceRecommendation(
                ref=K8sObjectRef(
                    kind="Deployment",
                    api_version="apps/v1",
                    namespace=namespace,
                    name=name,
                    uid=getattr(dep.metadata, "uid", None),
                ),
                container=cname,
                current=current,
                observed_p95=observed_p95,
                observed_p99=observed_p99,
                recommended=recommended,
                rationale=_rationale(current, observed_p95, observed_p99, rec_req),
                savings_estimate_cpu_cores=(current.requests.cpu_cores - rec_req.cpu_cores),
                savings_estimate_memory_mib=(current.requests.memory_mib - rec_req.memory_mib),
            )
        )
    return recommendations


async def propose_right_size_plan(
    *,
    prom: PromClient,
    apps_v1: Any,
    namespace: str,
    window_days: int = 7,
) -> RightSizePlan:
    deployments = await apps_v1.list_namespaced_deployment(namespace=namespace)
    all_recs: list[ResourceRecommendation] = []
    for dep in getattr(deployments, "items", []) or []:
        meta = getattr(dep, "metadata", None)
        if meta is None:
            continue
        recs = await analyze_deployment(
            prom=prom,
            apps_v1=apps_v1,
            namespace=namespace,
            name=meta.name,
            window_days=window_days,
        )
        all_recs.extend(recs)
    return RightSizePlan(
        namespace=namespace,
        window_days=window_days,
        recommendations=all_recs,
        narration=None,
        proposed_at=datetime.now(UTC),
    )
