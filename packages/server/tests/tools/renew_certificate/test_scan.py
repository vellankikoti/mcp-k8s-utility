from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from utility_server.tools.renew_certificate.scan import (
    _summarise_certificate,
    list_expiring_certificates,
)


def _cert_obj(name: str, namespace: str, days_until_expiry: int, secret_name: str = "tls-sec"):
    not_after = (
        (datetime.now(UTC) + timedelta(days=days_until_expiry)).isoformat().replace("+00:00", "Z")
    )
    return {
        "metadata": {"name": name, "namespace": namespace, "uid": f"u-{name}"},
        "spec": {
            "secretName": secret_name,
            "dnsNames": [f"{name}.example.com"],
            "issuerRef": {"name": "letsencrypt-prod"},
        },
        "status": {
            "notAfter": not_after,
            "conditions": [{"type": "Ready", "status": "True"}],
        },
    }


async def test_list_expiring_cluster_wide_filters_by_window():
    custom_api = MagicMock()
    custom_api.list_cluster_custom_object = AsyncMock(
        return_value={"items": [_cert_obj("a", "prod", 5), _cert_obj("b", "prod", 30)]}
    )
    out = await list_expiring_certificates(custom_api=custom_api, within_days=14)
    names = {c.ref.name for c in out}
    assert names == {"a"}


async def test_list_expiring_namespace_scoped():
    custom_api = MagicMock()
    custom_api.list_namespaced_custom_object = AsyncMock(
        return_value={"items": [_cert_obj("a", "prod", 2)]}
    )
    custom_api.list_cluster_custom_object = AsyncMock()
    out = await list_expiring_certificates(custom_api=custom_api, within_days=14, namespace="prod")
    assert len(out) == 1
    custom_api.list_cluster_custom_object.assert_not_awaited()


async def test_list_expiring_skips_cert_without_not_after():
    custom_api = MagicMock()
    custom_api.list_cluster_custom_object = AsyncMock(
        return_value={
            "items": [{"metadata": {"name": "bad", "namespace": "x"}, "spec": {}, "status": {}}]
        }
    )
    out = await list_expiring_certificates(custom_api=custom_api, within_days=14)
    assert out == []


def test_days_until_expiry_uses_ceiling_not_floor():
    """A cert expiring in 47.6 hours should report 2 days, not 1 (floor).

    This regression guards the math.ceil change in _summarise_certificate so that
    certs with e.g. 47h remaining are not shown as "1 day" to the operator.
    """
    # 47.6 hours from now
    not_after_str = (datetime.now(UTC) + timedelta(hours=47.6)).isoformat().replace("+00:00", "Z")
    obj = {
        "metadata": {"name": "tls-cert", "namespace": "prod", "uid": "u1"},
        "spec": {
            "secretName": "tls-sec",
            "dnsNames": ["svc.example.com"],
            "issuerRef": {"name": "issuer"},
        },
        "status": {
            "notAfter": not_after_str,
            "conditions": [{"type": "Ready", "status": "True"}],
        },
    }
    summary = _summarise_certificate(obj)
    assert summary is not None
    assert summary.days_until_expiry == 2, (
        f"Expected ceil(47.6h / 24) == 2, got {summary.days_until_expiry}"
    )
