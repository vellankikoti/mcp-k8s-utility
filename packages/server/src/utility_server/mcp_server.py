from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, cast

from fastmcp import FastMCP
from kubernetes_asyncio import client as k8s_client
from kubernetes_asyncio import config as k8s_config

from utility_server.models import RenewalPlan
from utility_server.tools.renew_certificate.execute import execute_renewal_plan
from utility_server.tools.renew_certificate.plan import propose_renewal_plan
from utility_server.tools.renew_certificate.scan import list_expiring_certificates

mcp: FastMCP = FastMCP("mcp-k8s-utility")

_api_client: Any = None
_custom_api: Any = None
_apps_api: Any = None


async def _get_k8s() -> tuple[Any, Any]:
    global _api_client, _custom_api, _apps_api
    if _api_client is None:
        kubeconfig = os.environ.get("KUBECONFIG")
        if kubeconfig:
            await k8s_config.load_kube_config(config_file=kubeconfig)
        else:
            try:
                await k8s_config.load_kube_config()
            except Exception:
                k8s_config.load_incluster_config()  # type: ignore[no-untyped-call]
        _api_client = k8s_client.ApiClient()
        _custom_api = k8s_client.CustomObjectsApi(_api_client)
        _apps_api = k8s_client.AppsV1Api(_api_client)
    return _custom_api, _apps_api


async def _restart_via_secureops(namespace: str, name: str) -> dict[str, Any]:
    """Bridge to secureops_server's restart_deployment tool."""
    from secureops_server.mcp_server import (  # type: ignore[import-untyped]
        restart_deployment_tool,
    )

    result = await restart_deployment_tool(namespace=namespace, name=name)
    return cast(dict[str, Any], result)


@mcp.tool(name="list_expiring_certificates")
async def list_expiring_certificates_tool(
    within_days: int = 14, namespace: str | None = None
) -> list[dict[str, Any]]:
    """Scan cert-manager Certificates expiring within `within_days` days."""
    custom_api, _ = await _get_k8s()
    summaries = await list_expiring_certificates(
        custom_api=custom_api, within_days=within_days, namespace=namespace
    )
    return [s.model_dump(mode="json") for s in summaries]


@mcp.tool(name="propose_certificate_renewal")
async def propose_certificate_renewal_tool(
    within_days: int = 14,
    force_during_business_hours: bool = False,
) -> dict[str, Any]:
    """Build a dry-run renewal plan with dependent-workload analysis."""
    custom_api, apps_api = await _get_k8s()
    certs = await list_expiring_certificates(custom_api=custom_api, within_days=within_days)
    plan = await propose_renewal_plan(
        apps_v1=apps_api,
        certificates=certs,
        within_days=within_days,
        force_during_business_hours=force_during_business_hours,
    )
    return plan.model_dump(mode="json")


@mcp.tool(name="execute_certificate_renewal")
async def execute_certificate_renewal_tool(
    plan: dict[str, Any],
    dry_run: bool = True,
) -> dict[str, Any]:
    """Apply a renewal plan. Writes only if dry_run=False AND business-hours gate passes.
    Every dependent rollout is routed through the secure-ops broker — policy-gated,
    short-lived-token authorized, audit-chained.
    """
    custom_api, _ = await _get_k8s()
    typed_plan = RenewalPlan.model_validate(plan)
    result = await execute_renewal_plan(
        custom_api=custom_api,
        plan=typed_plan,
        dry_run=dry_run,
        restart_deployment=_restart_via_secureops,
        now=datetime.now(UTC),
    )
    return result.model_dump(mode="json")


def run_stdio() -> None:
    mcp.run(transport="stdio")
