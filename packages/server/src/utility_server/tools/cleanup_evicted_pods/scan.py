from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from utility_server.models import EvictedPodSummary, K8sObjectRef


def _parse_time(value: Any) -> datetime | None:
    """kubernetes_asyncio returns datetime or ISO strings depending on version."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _owner(pod: Any) -> tuple[str | None, str | None]:
    refs = getattr(pod.metadata, "owner_references", None) or []
    for ref in refs:
        if getattr(ref, "controller", False):
            return getattr(ref, "kind", None), getattr(ref, "name", None)
    if refs:
        ref = refs[0]
        return getattr(ref, "kind", None), getattr(ref, "name", None)
    return None, None


def _is_evicted(pod: Any) -> bool:
    status = getattr(pod, "status", None)
    if status is None:
        return False
    if getattr(status, "phase", None) != "Failed":
        return False
    return getattr(status, "reason", None) == "Evicted"


def _summarise_pod(pod: Any, now: datetime) -> EvictedPodSummary | None:
    if not _is_evicted(pod):
        return None
    meta = pod.metadata
    status = pod.status
    evicted_at = _parse_time(getattr(status, "start_time", None)) or _parse_time(
        getattr(meta, "creation_timestamp", None)
    )
    age_hours = None
    if evicted_at is not None:
        age_hours = round((now - evicted_at).total_seconds() / 3600, 2)
    owner_kind, owner_name = _owner(pod)
    return EvictedPodSummary(
        ref=K8sObjectRef(
            kind="Pod",
            api_version="v1",
            namespace=meta.namespace,
            name=meta.name,
            uid=meta.uid,
        ),
        eviction_reason=getattr(status, "reason", "Evicted") or "Evicted",
        eviction_message=getattr(status, "message", "") or "",
        evicted_at=evicted_at,
        age_hours=age_hours,
        node_name=getattr(pod.spec, "node_name", None) if getattr(pod, "spec", None) else None,
        owner_kind=owner_kind,
        owner_name=owner_name,
    )


async def list_evicted_pods(
    core_v1: Any, namespace: str | None = None, now: datetime | None = None
) -> list[EvictedPodSummary]:
    """List pods in Failed/Evicted state. Never touches running workloads."""
    moment = now or datetime.now(UTC)
    # Kubernetes supports a fieldSelector; this narrows the query server-side.
    field_selector = "status.phase=Failed"
    if namespace:
        result = await core_v1.list_namespaced_pod(
            namespace=namespace, field_selector=field_selector
        )
    else:
        result = await core_v1.list_pod_for_all_namespaces(field_selector=field_selector)
    out: list[EvictedPodSummary] = []
    for pod in getattr(result, "items", None) or []:
        summary = _summarise_pod(pod, moment)
        if summary is not None:
            out.append(summary)
    return out
