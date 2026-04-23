from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from utility_server.models import (
    CertificateSummary,
    K8sObjectRef,
    RenewalPlan,
    RenewalStep,
)

_FORCE_RENEW_ANNOTATION = "cert-manager.io/force-renew-at"


async def _find_dependents(apps_v1: Any, namespace: str, secret_name: str) -> list[K8sObjectRef]:
    """Find Deployments in namespace whose pods mount the given Secret."""
    deployments = await apps_v1.list_namespaced_deployment(namespace=namespace)
    out: list[K8sObjectRef] = []
    for dep in getattr(deployments, "items", []) or []:
        if _deployment_mounts_secret(dep, secret_name):
            out.append(
                K8sObjectRef(
                    kind="Deployment",
                    api_version="apps/v1",
                    namespace=dep.metadata.namespace,
                    name=dep.metadata.name,
                    uid=dep.metadata.uid,
                )
            )
    return out


def _deployment_mounts_secret(deployment: Any, secret_name: str) -> bool:
    spec = getattr(deployment, "spec", None)
    if spec is None:
        return False
    template = getattr(spec, "template", None)
    pod_spec = getattr(template, "spec", None) if template else None
    if pod_spec is None:
        return False
    # 1. Volumes sourced from the Secret
    for volume in getattr(pod_spec, "volumes", None) or []:
        secret_vol = getattr(volume, "secret", None)
        if secret_vol is not None and getattr(secret_vol, "secret_name", None) == secret_name:
            return True
    # 2. envFrom / env valueFrom secretKeyRef
    for container in getattr(pod_spec, "containers", None) or []:
        for env_src in getattr(container, "env_from", None) or []:
            sec_ref = getattr(env_src, "secret_ref", None)
            if sec_ref is not None and getattr(sec_ref, "name", None) == secret_name:
                return True
        for env_var in getattr(container, "env", None) or []:
            val_from = getattr(env_var, "value_from", None)
            sec_key_ref = getattr(val_from, "secret_key_ref", None) if val_from else None
            if sec_key_ref is not None and getattr(sec_key_ref, "name", None) == secret_name:
                return True
    return False


async def propose_renewal_plan(
    *,
    apps_v1: Any,
    certificates: list[CertificateSummary],
    within_days: int,
    force_during_business_hours: bool = False,
    now: datetime | None = None,
) -> RenewalPlan:
    """Build a RenewalPlan. Does not mutate cluster state."""
    moment = now or datetime.now(UTC)
    steps: list[RenewalStep] = []
    for cert in certificates:
        dependents = await _find_dependents(apps_v1, cert.ref.namespace, cert.secret_name)
        steps.append(
            RenewalStep(
                certificate=cert.ref,
                annotation_patch={
                    "metadata": {
                        "annotations": {_FORCE_RENEW_ANNOTATION: moment.isoformat()},
                    }
                },
                dependent_rollouts=dependents,
            )
        )
    return RenewalPlan(
        window_days=within_days,
        steps=steps,
        force_during_business_hours=force_during_business_hours,
        proposed_at=moment,
    )


def _parse_bh_int(env_name: str, default: int) -> int:
    """Read an integer env var. Returns default on missing or invalid value."""
    import os

    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_bh_days(env_name: str, default: frozenset[int]) -> frozenset[int]:
    """Read a comma-separated 0-6 weekday list env var. Returns default on error."""
    import os

    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return default
    try:
        days = frozenset(int(d.strip()) for d in raw.split(",") if d.strip())
        if not days or not all(0 <= d <= 6 for d in days):
            return default
        return days
    except ValueError:
        return default


_DEFAULT_BH_START = 13
_DEFAULT_BH_END = 21
_DEFAULT_BH_DAYS: frozenset[int] = frozenset({0, 1, 2, 3, 4})  # Mon-Fri


def is_business_hours(moment: datetime | None = None) -> bool:
    """Return True if ``moment`` falls within the configured business-hours window.

    Defaults to UTC 13:00-21:00 Mon-Fri. Override with env vars:
    - ``UTILITY_BUSINESS_HOURS_START_UTC``: hour (int, 0-23), default 13.
    - ``UTILITY_BUSINESS_HOURS_END_UTC``: hour (int, 0-23), default 21.
    - ``UTILITY_BUSINESS_HOURS_DAYS``: comma-separated 0-6 (0=Mon), default "0,1,2,3,4".

    Invalid env values fall back to defaults silently — never raises.
    """
    m = moment or datetime.now(UTC)
    start = _parse_bh_int("UTILITY_BUSINESS_HOURS_START_UTC", _DEFAULT_BH_START)
    end = _parse_bh_int("UTILITY_BUSINESS_HOURS_END_UTC", _DEFAULT_BH_END)
    days = _parse_bh_days("UTILITY_BUSINESS_HOURS_DAYS", _DEFAULT_BH_DAYS)
    if m.weekday() not in days:
        return False
    return start <= m.hour < end
