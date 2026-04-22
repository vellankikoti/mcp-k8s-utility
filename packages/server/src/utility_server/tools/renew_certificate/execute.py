from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from utility_server.models import (
    K8sObjectRef,
    RenewalPlan,
    RenewalResult,
    RenewalStepResult,
)
from utility_server.tools.renew_certificate.plan import is_business_hours

_CERT_MANAGER_GROUP = "cert-manager.io"
_CERT_MANAGER_VERSION = "v1"
_CERT_MANAGER_PLURAL = "certificates"


async def _annotate_certificate(custom_api: Any, cert: K8sObjectRef, patch: dict[str, Any]) -> None:
    await custom_api.patch_namespaced_custom_object(
        group=_CERT_MANAGER_GROUP,
        version=_CERT_MANAGER_VERSION,
        namespace=cert.namespace,
        plural=_CERT_MANAGER_PLURAL,
        name=cert.name,
        body=patch,
    )


RestartDeploymentFn = Callable[[str, str], Awaitable[dict[str, Any]]]
"""Signature of secureops_server.mcp_server.restart_deployment_tool:
   `async def restart_deployment_tool(namespace: str, name: str) -> dict[str, Any]`."""


async def execute_renewal_plan(
    *,
    custom_api: Any,
    plan: RenewalPlan,
    dry_run: bool = True,
    restart_deployment: RestartDeploymentFn,
    now: datetime | None = None,
) -> RenewalResult:
    """Apply a RenewalPlan.

    If dry_run=True, returns a RenewalResult with status=skipped_dry_run for every step.
    If business-hours and not force_during_business_hours, refuses globally.
    Otherwise, for each step: patch the Certificate, then trigger rollout-restart of
    each dependent via the secure-ops broker function `restart_deployment`.
    """
    moment = now or datetime.now(UTC)

    if not dry_run and is_business_hours(moment) and not plan.force_during_business_hours:
        return RenewalResult(
            dry_run=False,
            executed_at=moment,
            steps=[],
            refused=True,
            refusal_reason=(
                "Renewal refused: business hours (UTC 13:00-21:00 Mon-Fri). "
                "Pass force_during_business_hours=True with SRE ack to override."
            ),
        )

    step_results: list[RenewalStepResult] = []
    for step in plan.steps:
        if dry_run:
            step_results.append(
                RenewalStepResult(
                    certificate=step.certificate,
                    status="skipped_dry_run",
                    rollouts_triggered=[],
                )
            )
            continue
        try:
            await _annotate_certificate(custom_api, step.certificate, step.annotation_patch)
        except Exception as e:
            step_results.append(
                RenewalStepResult(
                    certificate=step.certificate,
                    status="failed",
                    rollouts_triggered=[],
                    error=repr(e),
                )
            )
            continue
        triggered: list[K8sObjectRef] = []
        for dep in step.dependent_rollouts:
            try:
                await restart_deployment(dep.namespace, dep.name)
                triggered.append(dep)
            except Exception as e:
                step_results.append(
                    RenewalStepResult(
                        certificate=step.certificate,
                        status="failed",
                        rollouts_triggered=triggered,
                        error=f"rollout-restart failed for {dep.namespace}/{dep.name}: {e!r}",
                    )
                )
                break
        else:
            step_results.append(
                RenewalStepResult(
                    certificate=step.certificate,
                    status="annotated",
                    rollouts_triggered=triggered,
                )
            )
    return RenewalResult(
        dry_run=dry_run,
        executed_at=moment,
        steps=step_results,
    )
