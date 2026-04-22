from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any, cast

from fastmcp import FastMCP
from kubernetes_asyncio import client as k8s_client
from kubernetes_asyncio import config as k8s_config

from utility_server import __version__
from utility_server.llm.adapter import UtilityLLM
from utility_server.models import CleanupPlan, RenewalPlan, RetentionCleanupPlan
from utility_server.opensearch_client import OpenSearchClient
from utility_server.prom_client import PromClient
from utility_server.tools.cleanup_evicted_pods.execute import execute_cleanup_plan
from utility_server.tools.cleanup_evicted_pods.plan import propose_cleanup_plan
from utility_server.tools.cleanup_evicted_pods.scan import list_evicted_pods
from utility_server.tools.opensearch_retention.execute import execute_retention_plan
from utility_server.tools.opensearch_retention.plan import propose_retention_plan
from utility_server.tools.opensearch_retention.scan import list_old_indices
from utility_server.tools.renew_certificate.execute import execute_renewal_plan
from utility_server.tools.renew_certificate.plan import propose_renewal_plan
from utility_server.tools.renew_certificate.scan import list_expiring_certificates
from utility_server.tools.right_size_workload.analyze import propose_right_size_plan
from utility_server.tools.right_size_workload.narrate import narrate_plan
from utility_server.tools.tune_alert_thresholds.analyze import list_noisy_alerts
from utility_server.tools.tune_alert_thresholds.propose import propose_alert_tuning

mcp: FastMCP = FastMCP("mcp-k8s-utility", version=__version__)

_api_client: Any = None
_custom_api: Any = None
_apps_api: Any = None
_core_api: Any = None


async def _get_k8s() -> tuple[Any, Any]:
    await _init_k8s()
    return _custom_api, _apps_api


async def _get_core() -> Any:
    await _init_k8s()
    return _core_api


async def _init_k8s() -> None:
    global _api_client, _custom_api, _apps_api, _core_api
    if _api_client is not None:
        return
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
    _core_api = k8s_client.CoreV1Api(_api_client)


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


@mcp.tool(name="propose_right_size_plan")
async def propose_right_size_plan_tool(namespace: str, window_days: int = 7) -> dict[str, Any]:
    """Prometheus-driven right-sizing recommendations for Deployments in a namespace.

    Dry-run by design: this tool only READS metrics and workload specs; it never writes.
    LLM narration is attached if a provider is configured; otherwise a deterministic
    statistical summary is returned.
    """
    _, apps_api = await _get_k8s()
    prom = PromClient()
    plan = await propose_right_size_plan(
        prom=prom, apps_v1=apps_api, namespace=namespace, window_days=window_days
    )
    llm = UtilityLLM.from_env()
    plan = await narrate_plan(plan, llm)
    return plan.model_dump(mode="json")


@mcp.tool(name="list_evicted_pods")
async def list_evicted_pods_tool(namespace: str | None = None) -> list[dict[str, Any]]:
    """List pods in Failed/Evicted state. Read-only."""
    core_api = await _get_core()
    pods = await list_evicted_pods(core_api, namespace=namespace)
    return [p.model_dump(mode="json") for p in pods]


@mcp.tool(name="propose_cleanup_plan")
async def propose_cleanup_plan_tool(
    namespace: str | None = None,
    min_age_hours: float = 1.0,
    max_deletes_per_namespace: int = 20,
) -> dict[str, Any]:
    """Produce a dry-run cleanup plan with per-namespace rate limits and age gates."""
    core_api = await _get_core()
    plan = await propose_cleanup_plan(
        core_v1=core_api,
        namespace=namespace,
        min_age_hours=min_age_hours,
        max_deletes_per_namespace=max_deletes_per_namespace,
    )
    return plan.model_dump(mode="json")


@mcp.tool(name="execute_cleanup_plan")
async def execute_cleanup_plan_tool(plan: dict[str, Any], dry_run: bool = True) -> dict[str, Any]:
    """Apply a cleanup plan. Only pods marked will_delete=True are touched."""
    core_api = await _get_core()
    typed_plan = CleanupPlan.model_validate(plan)
    result = await execute_cleanup_plan(core_v1=core_api, plan=typed_plan, dry_run=dry_run)
    return result.model_dump(mode="json")


@mcp.tool(name="list_noisy_alerts")
async def list_noisy_alerts_tool(
    window_hours: float = 24.0, min_flaps_per_hour: float = 0.5
) -> list[dict[str, Any]]:
    """Query Prometheus for alerts that flapped often in the given window. Read-only."""
    prom = PromClient()
    alerts = await list_noisy_alerts(
        prom=prom, window_hours=window_hours, min_flaps_per_hour=min_flaps_per_hour
    )
    return [a.model_dump(mode="json") for a in alerts]


@mcp.tool(name="propose_alert_tuning")
async def propose_alert_tuning_tool(
    window_hours: float = 24.0, min_flaps_per_hour: float = 0.5
) -> dict[str, Any]:
    """Advisory: per-alert tuning recommendations (recommended `for:` duration).

    Critical-severity alerts are flagged for human review; nothing is applied.
    LLM narration if a provider is configured; deterministic summary otherwise.
    """
    prom = PromClient()
    alerts = await list_noisy_alerts(
        prom=prom, window_hours=window_hours, min_flaps_per_hour=min_flaps_per_hour
    )
    llm = UtilityLLM.from_env()
    report = await propose_alert_tuning(
        alerts=alerts,
        llm=llm,
        window_hours=window_hours,
        min_flaps_per_hour=min_flaps_per_hour,
    )
    return report.model_dump(mode="json")


@mcp.tool(name="list_old_opensearch_indices")
async def list_old_opensearch_indices_tool(
    older_than_days: float, index_patterns: list[str]
) -> list[dict[str, Any]]:
    """List OpenSearch indices older than `older_than_days` matching any of `index_patterns`.
    Read-only. Returns empty list if OPENSEARCH_URL is unset or the cluster is unreachable."""
    client = OpenSearchClient()
    indices = await list_old_indices(
        client=client, older_than_days=older_than_days, index_patterns=index_patterns
    )
    return [i.model_dump(mode="json") for i in indices]


@mcp.tool(name="propose_retention_cleanup")
async def propose_retention_cleanup_tool(
    older_than_days: float,
    index_patterns: list[str],
    max_deletes: int = 50,
) -> dict[str, Any]:
    """Dry-run retention cleanup with size-reclaim preview, pattern gate, retention-tag safety,
    and per-call rate limit. LLM narration if a provider is configured, deterministic fallback
    otherwise."""
    client = OpenSearchClient()
    llm = UtilityLLM.from_env()
    plan = await propose_retention_plan(
        client=client,
        older_than_days=older_than_days,
        index_patterns=index_patterns,
        max_deletes=max_deletes,
        llm=llm,
    )
    return plan.model_dump(mode="json")


@mcp.tool(name="execute_retention_cleanup")
async def execute_retention_cleanup_tool(
    plan: dict[str, Any], dry_run: bool = True
) -> dict[str, Any]:
    """Apply a retention cleanup plan. Only indices marked will_delete=True are touched."""
    client = OpenSearchClient()
    typed_plan = RetentionCleanupPlan.model_validate(plan)
    result = await execute_retention_plan(client=client, plan=typed_plan, dry_run=dry_run)
    return result.model_dump(mode="json")


def run_stdio() -> None:
    mcp.run(transport="stdio")
