from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from utility_server.models import CertificateSummary, K8sObjectRef

_CERT_MANAGER_GROUP = "cert-manager.io"
_CERT_MANAGER_VERSION = "v1"
_CERT_MANAGER_PLURAL = "certificates"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _ready_condition(conditions: list[dict[str, Any]] | None) -> bool:
    return any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions or [])


def _summarise_certificate(obj: dict[str, Any]) -> CertificateSummary | None:
    meta = obj.get("metadata") or {}
    spec = obj.get("spec") or {}
    status = obj.get("status") or {}
    not_after = _parse_iso(status.get("notAfter"))
    if not_after is None:
        return None
    now = datetime.now(UTC)
    days = math.ceil((not_after - now).total_seconds() / 86400)
    return CertificateSummary(
        ref=K8sObjectRef(
            kind="Certificate",
            api_version=f"{_CERT_MANAGER_GROUP}/{_CERT_MANAGER_VERSION}",
            namespace=meta.get("namespace", ""),
            name=meta.get("name", ""),
            uid=meta.get("uid"),
        ),
        secret_name=spec.get("secretName") or "",
        dns_names=list(spec.get("dnsNames") or []),
        not_after=not_after,
        days_until_expiry=days,
        issuer=(spec.get("issuerRef") or {}).get("name"),
        is_ready=_ready_condition(status.get("conditions")),
    )


async def list_expiring_certificates(
    custom_api: Any, within_days: int = 14, namespace: str | None = None
) -> list[CertificateSummary]:
    """Scan cert-manager Certificate CRs; return those expiring within `within_days`."""
    if namespace:
        result = await custom_api.list_namespaced_custom_object(
            group=_CERT_MANAGER_GROUP,
            version=_CERT_MANAGER_VERSION,
            namespace=namespace,
            plural=_CERT_MANAGER_PLURAL,
        )
    else:
        result = await custom_api.list_cluster_custom_object(
            group=_CERT_MANAGER_GROUP,
            version=_CERT_MANAGER_VERSION,
            plural=_CERT_MANAGER_PLURAL,
        )
    items = result.get("items") if isinstance(result, dict) else []
    out: list[CertificateSummary] = []
    for obj in items or []:
        summary = _summarise_certificate(obj)
        if summary is None:
            continue
        if summary.days_until_expiry <= within_days:
            out.append(summary)
    return out
