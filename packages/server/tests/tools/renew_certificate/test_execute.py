from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from utility_server.models import (
    K8sObjectRef,
    RenewalPlan,
    RenewalStep,
)
from utility_server.tools.renew_certificate.execute import execute_renewal_plan


def _step(cert_name: str = "payments", dep_name: str = "payments-api") -> RenewalStep:
    return RenewalStep(
        certificate=K8sObjectRef(
            kind="Certificate",
            api_version="cert-manager.io/v1",
            namespace="prod",
            name=cert_name,
            uid="u-cert",
        ),
        annotation_patch={
            "metadata": {
                "annotations": {"cert-manager.io/force-renew-at": "2026-05-06T14:00:00+00:00"}
            }
        },
        dependent_rollouts=[
            K8sObjectRef(
                kind="Deployment",
                api_version="apps/v1",
                namespace="prod",
                name=dep_name,
                uid="u-dep",
            )
        ],
    )


def _plan(force: bool = False) -> RenewalPlan:
    return RenewalPlan(
        window_days=14,
        steps=[_step()],
        force_during_business_hours=force,
        proposed_at=datetime.now(UTC),
    )


def _off_hours() -> datetime:
    # Sat 00:00 UTC — not business hours
    return datetime(2026, 5, 9, 0, 0, tzinfo=UTC)


def _business_hours() -> datetime:
    # Wed 14:00 UTC — business hours
    return datetime(2026, 5, 6, 14, 0, tzinfo=UTC)


async def test_dry_run_skips_all():
    custom_api = MagicMock()
    custom_api.patch_namespaced_custom_object = AsyncMock()
    restart = AsyncMock()
    result = await execute_renewal_plan(
        custom_api=custom_api,
        plan=_plan(),
        dry_run=True,
        restart_deployment=restart,
        now=_off_hours(),
    )
    assert result.dry_run is True
    assert result.steps[0].status == "skipped_dry_run"
    custom_api.patch_namespaced_custom_object.assert_not_awaited()
    restart.assert_not_awaited()


async def test_business_hours_without_force_refuses():
    custom_api = MagicMock()
    custom_api.patch_namespaced_custom_object = AsyncMock()
    restart = AsyncMock()
    result = await execute_renewal_plan(
        custom_api=custom_api,
        plan=_plan(force=False),
        dry_run=False,
        restart_deployment=restart,
        now=_business_hours(),
    )
    assert result.refused is True
    assert "business hours" in (result.refusal_reason or "").lower()
    custom_api.patch_namespaced_custom_object.assert_not_awaited()
    restart.assert_not_awaited()


async def test_off_hours_execution_annotates_and_restarts():
    custom_api = MagicMock()
    custom_api.patch_namespaced_custom_object = AsyncMock()
    restart = AsyncMock(return_value={"status": "allowed_executed"})
    result = await execute_renewal_plan(
        custom_api=custom_api,
        plan=_plan(),
        dry_run=False,
        restart_deployment=restart,
        now=_off_hours(),
    )
    assert result.refused is False
    assert result.steps[0].status == "annotated"
    assert result.steps[0].rollouts_triggered[0].name == "payments-api"
    custom_api.patch_namespaced_custom_object.assert_awaited_once()
    restart.assert_awaited_once_with("prod", "payments-api")


async def test_forced_business_hours_executes():
    custom_api = MagicMock()
    custom_api.patch_namespaced_custom_object = AsyncMock()
    restart = AsyncMock(return_value={"status": "allowed_executed"})
    result = await execute_renewal_plan(
        custom_api=custom_api,
        plan=_plan(force=True),
        dry_run=False,
        restart_deployment=restart,
        now=_business_hours(),
    )
    assert result.refused is False
    assert result.steps[0].status == "annotated"


async def test_annotate_failure_yields_failed_status():
    custom_api = MagicMock()
    custom_api.patch_namespaced_custom_object = AsyncMock(side_effect=RuntimeError("boom"))
    restart = AsyncMock()
    result = await execute_renewal_plan(
        custom_api=custom_api,
        plan=_plan(),
        dry_run=False,
        restart_deployment=restart,
        now=_off_hours(),
    )
    assert result.steps[0].status == "failed"
    assert "boom" in (result.steps[0].error or "")
    restart.assert_not_awaited()


async def test_restart_failure_reports_partial():
    custom_api = MagicMock()
    custom_api.patch_namespaced_custom_object = AsyncMock()
    restart = AsyncMock(side_effect=RuntimeError("denied_opa"))
    result = await execute_renewal_plan(
        custom_api=custom_api,
        plan=_plan(),
        dry_run=False,
        restart_deployment=restart,
        now=_off_hours(),
    )
    assert result.steps[0].status == "failed"
    assert "rollout-restart failed" in (result.steps[0].error or "")
