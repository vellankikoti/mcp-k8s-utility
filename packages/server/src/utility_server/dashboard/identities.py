from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class PerActionServiceAccount:
    name: str
    namespace: str
    created_at: datetime | None
    age_hours: float | None


_PREFIX = "secureops-action-"


def _age_hours(created: datetime | None, now: datetime) -> float | None:
    if created is None:
        return None
    return round((now - created).total_seconds() / 3600.0, 2)


async def _list_action_sas() -> list[PerActionServiceAccount]:
    """Internal — returns [] on any failure (missing kubeconfig, unreachable cluster)."""
    kubeconfig = os.environ.get("KUBECONFIG") or os.path.expanduser("~/.kube/config")
    if not os.path.exists(kubeconfig):
        return []
    from kubernetes_asyncio import client as k8s_client
    from kubernetes_asyncio import config as k8s_config

    now = datetime.now(UTC)
    try:
        await k8s_config.load_kube_config(config_file=kubeconfig)
        api = k8s_client.ApiClient()
        core = k8s_client.CoreV1Api(api)
        result = await core.list_service_account_for_all_namespaces()
    except Exception:
        return []

    out: list[PerActionServiceAccount] = []
    for sa in getattr(result, "items", None) or []:
        name = getattr(sa.metadata, "name", "") or ""
        if not name.startswith(_PREFIX):
            continue
        created = getattr(sa.metadata, "creation_timestamp", None)
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            except ValueError:
                created = None
        if isinstance(created, datetime) and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        out.append(
            PerActionServiceAccount(
                name=name,
                namespace=getattr(sa.metadata, "namespace", "") or "",
                created_at=created,
                age_hours=_age_hours(created, now),
            )
        )
    return sorted(out, key=lambda s: s.created_at or now, reverse=True)


async def list_action_sas(timeout_s: float = 5.0) -> list[PerActionServiceAccount]:
    """Bounded list call with graceful timeout."""
    try:
        return await asyncio.wait_for(_list_action_sas(), timeout=timeout_s)
    except TimeoutError:
        return []
