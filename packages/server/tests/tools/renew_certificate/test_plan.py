from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from utility_server.models import CertificateSummary, K8sObjectRef
from utility_server.tools.renew_certificate.plan import (
    is_business_hours,
    propose_renewal_plan,
)


def _summary(cert_name: str = "payments", secret_name: str = "tls-sec") -> CertificateSummary:
    return CertificateSummary(
        ref=K8sObjectRef(
            kind="Certificate",
            api_version="cert-manager.io/v1",
            namespace="prod",
            name=cert_name,
            uid="u-cert",
        ),
        secret_name=secret_name,
        dns_names=["payments.example.com"],
        not_after=datetime.now(UTC) + timedelta(days=3),
        days_until_expiry=3,
        issuer="letsencrypt-prod",
        is_ready=True,
    )


def _deployment_mounting(secret_name: str, name: str = "payments-api"):
    d = MagicMock()
    d.metadata.name = name
    d.metadata.namespace = "prod"
    d.metadata.uid = f"u-{name}"
    vol = MagicMock()
    vol.secret = MagicMock()
    vol.secret.secret_name = secret_name
    d.spec.template.spec.volumes = [vol]
    d.spec.template.spec.containers = []
    return d


async def test_propose_plan_identifies_dependents():
    apps_v1 = MagicMock()
    apps_v1.list_namespaced_deployment = AsyncMock(
        return_value=MagicMock(items=[_deployment_mounting("tls-sec")])
    )
    plan = await propose_renewal_plan(
        apps_v1=apps_v1,
        certificates=[_summary()],
        within_days=14,
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].dependent_rollouts[0].name == "payments-api"
    assert "metadata" in plan.steps[0].annotation_patch


async def test_propose_plan_deployments_not_mounting_secret_excluded():
    apps_v1 = MagicMock()
    apps_v1.list_namespaced_deployment = AsyncMock(
        return_value=MagicMock(items=[_deployment_mounting("other-sec")])
    )
    plan = await propose_renewal_plan(apps_v1=apps_v1, certificates=[_summary()], within_days=14)
    assert plan.steps[0].dependent_rollouts == []


def test_is_business_hours_utc_window():
    # Wed 14:00 UTC — business hours
    assert is_business_hours(datetime(2026, 5, 6, 14, 0, tzinfo=UTC)) is True
    # Sat 14:00 UTC — weekend
    assert is_business_hours(datetime(2026, 5, 9, 14, 0, tzinfo=UTC)) is False
    # Wed 04:00 UTC — early morning
    assert is_business_hours(datetime(2026, 5, 6, 4, 0, tzinfo=UTC)) is False
