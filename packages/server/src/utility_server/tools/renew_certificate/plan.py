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


def is_business_hours(moment: datetime | None = None) -> bool:
    """UTC 13:00-21:00 on weekdays covers most business-hour risk windows."""
    m = moment or datetime.now(UTC)
    if m.weekday() >= 5:
        return False
    return 13 <= m.hour < 21
