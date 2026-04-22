from __future__ import annotations

import os
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from utility_server.models import (
    CleanupCandidate,
    CleanupPlan,
    EvictedPodSummary,
)
from utility_server.tools.cleanup_evicted_pods.scan import list_evicted_pods

_ENV_ALLOWLIST = "UTILITY_CLEANUP_NAMESPACE_ALLOWLIST"


def _parse_allowlist() -> list[str]:
    raw = os.environ.get(_ENV_ALLOWLIST, "").strip()
    if not raw:
        return []
    return [n.strip() for n in raw.split(",") if n.strip()]


def _gate(
    summary: EvictedPodSummary,
    *,
    min_age_hours: float,
    namespace_allowlist: list[str],
    per_ns_count: dict[str, int],
    max_deletes_per_namespace: int,
) -> tuple[bool, str | None]:
    """Apply policy gates. Returns (will_delete, skip_reason)."""
    ns = summary.ref.namespace
    if namespace_allowlist and ns not in namespace_allowlist:
        return False, f"namespace {ns} not in allowlist"
    if summary.age_hours is None:
        return False, "unknown eviction timestamp"
    if summary.age_hours < min_age_hours:
        return False, f"too recent (age={summary.age_hours:.2f}h < min={min_age_hours}h)"
    if per_ns_count[ns] >= max_deletes_per_namespace:
        return False, f"rate limit reached in namespace ({max_deletes_per_namespace} per call)"
    return True, None


async def propose_cleanup_plan(
    *,
    core_v1: Any,
    namespace: str | None = None,
    min_age_hours: float = 1.0,
    max_deletes_per_namespace: int = 20,
    namespace_allowlist: list[str] | None = None,
    now: datetime | None = None,
) -> CleanupPlan:
    moment = now or datetime.now(UTC)
    allowlist = namespace_allowlist if namespace_allowlist is not None else _parse_allowlist()
    pods = await list_evicted_pods(core_v1, namespace=namespace, now=moment)

    # Sort oldest first so rate-limit preserves the most-stable candidates.
    pods.sort(key=lambda p: p.evicted_at or moment)

    per_ns: dict[str, int] = defaultdict(int)
    candidates: list[CleanupCandidate] = []
    for p in pods:
        will_delete, skip_reason = _gate(
            p,
            min_age_hours=min_age_hours,
            namespace_allowlist=allowlist,
            per_ns_count=per_ns,
            max_deletes_per_namespace=max_deletes_per_namespace,
        )
        if will_delete:
            per_ns[p.ref.namespace] += 1
        candidates.append(CleanupCandidate(pod=p, will_delete=will_delete, skip_reason=skip_reason))
    return CleanupPlan(
        namespace=namespace,
        min_age_hours=min_age_hours,
        max_deletes_per_namespace=max_deletes_per_namespace,
        namespace_allowlist=allowlist,
        candidates=candidates,
        proposed_at=moment,
    )
