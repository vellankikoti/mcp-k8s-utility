from __future__ import annotations

from typing import Any

from utility_server.prom_client import PromClient


async def run_list_evicted_pods() -> dict[str, Any]:
    """Invoke list_evicted_pods against the ambient kubeconfig."""
    from utility_server.mcp_server import _get_core
    from utility_server.tools.cleanup_evicted_pods.scan import list_evicted_pods

    try:
        core = await _get_core()
        pods = await list_evicted_pods(core, namespace=None)
        return {
            "ok": True,
            "count": len(pods),
            "pods": [p.model_dump(mode="json") for p in pods[:10]],
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def run_propose_cleanup_plan() -> dict[str, Any]:
    """Dry-run cleanup plan with safe defaults."""
    from utility_server.mcp_server import _get_core
    from utility_server.tools.cleanup_evicted_pods.plan import propose_cleanup_plan

    try:
        core = await _get_core()
        plan = await propose_cleanup_plan(
            core_v1=core, min_age_hours=1.0, max_deletes_per_namespace=20
        )
        return {
            "ok": True,
            "candidates": len(plan.candidates),
            "will_delete": sum(1 for c in plan.candidates if c.will_delete),
            "first_candidates": [c.model_dump(mode="json") for c in plan.candidates[:5]],
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


async def run_propose_alert_tuning(window_hours: float = 24.0) -> dict[str, Any]:
    """Alert tuning recommendations — read-only PromQL."""
    from utility_server.llm.adapter import UtilityLLM
    from utility_server.tools.tune_alert_thresholds.analyze import list_noisy_alerts
    from utility_server.tools.tune_alert_thresholds.propose import propose_alert_tuning

    try:
        prom = PromClient()
        llm = UtilityLLM.from_env()
        alerts = await list_noisy_alerts(
            prom=prom, window_hours=window_hours, min_flaps_per_hour=0.5
        )
        report = await propose_alert_tuning(
            alerts=alerts,
            llm=llm,
            window_hours=window_hours,
            min_flaps_per_hour=0.5,
        )
        return {
            "ok": True,
            "window_hours": report.window_hours,
            "findings": len(report.findings),
            "narration": report.narration,
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


DEMOS: dict[str, Any] = {
    "evicted-pods": run_list_evicted_pods,
    "cleanup-plan": run_propose_cleanup_plan,
    "alert-tuning": run_propose_alert_tuning,
}
