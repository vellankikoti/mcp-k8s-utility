from __future__ import annotations

from datetime import UTC, datetime

from utility_server.llm.adapter import Provider, UtilityLLM
from utility_server.models import (
    K8sObjectRef,
    ResourceQuantities,
    ResourceRecommendation,
    RightSizePlan,
    WorkloadResources,
)
from utility_server.tools.right_size_workload.narrate import narrate_plan


def _plan_with_one_rec() -> RightSizePlan:
    ref = K8sObjectRef(
        kind="Deployment",
        api_version="apps/v1",
        namespace="prod",
        name="api",
    )
    cur = WorkloadResources(requests=ResourceQuantities(cpu_cores=0.5, memory_mib=256.0))
    obs95 = ResourceQuantities(cpu_cores=0.1, memory_mib=60.0)
    obs99 = ResourceQuantities(cpu_cores=0.15, memory_mib=80.0)
    rec = WorkloadResources(requests=ResourceQuantities(cpu_cores=0.2, memory_mib=96.0))
    r = ResourceRecommendation(
        ref=ref,
        container="app",
        current=cur,
        observed_p95=obs95,
        observed_p99=obs99,
        recommended=rec,
        rationale="because",
        savings_estimate_cpu_cores=0.3,
        savings_estimate_memory_mib=160.0,
    )
    return RightSizePlan(
        namespace="prod",
        window_days=7,
        recommendations=[r],
        narration=None,
        proposed_at=datetime.now(UTC),
    )


async def test_narrate_falls_back_to_deterministic_when_llm_disabled():
    llm = UtilityLLM(Provider.DISABLED)
    plan = await narrate_plan(_plan_with_one_rec(), llm)
    assert plan.narration is not None
    assert "prod" in plan.narration


async def test_narrate_empty_plan_reports_none_found():
    llm = UtilityLLM(Provider.DISABLED)
    empty = RightSizePlan(
        namespace="staging",
        window_days=7,
        recommendations=[],
        narration=None,
        proposed_at=datetime.now(UTC),
    )
    out = await narrate_plan(empty, llm)
    assert out.narration and "No right-sizing candidates" in out.narration
