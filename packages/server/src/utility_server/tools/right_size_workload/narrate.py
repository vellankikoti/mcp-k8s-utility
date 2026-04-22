from __future__ import annotations

from utility_server.llm.adapter import UtilityLLM
from utility_server.models import RightSizePlan


def _deterministic_summary(plan: RightSizePlan) -> str:
    total_cpu = sum(r.savings_estimate_cpu_cores for r in plan.recommendations)
    total_mem = sum(r.savings_estimate_memory_mib for r in plan.recommendations)
    n = len(plan.recommendations)
    if n == 0:
        return f"No right-sizing candidates found in namespace {plan.namespace}."
    direction = "save" if total_cpu > 0 or total_mem > 0 else "request more than observed"
    return (
        f"Analyzed {n} container(s) in namespace {plan.namespace} over "
        f"{plan.window_days}d. Total delta vs current requests: "
        f"{total_cpu:+.3f} CPU cores, {total_mem:+.0f} MiB memory "
        f"(positive = would {direction})."
    )


async def narrate_plan(plan: RightSizePlan, llm: UtilityLLM) -> RightSizePlan:
    """Attach narration to the plan. LLM-preferred; deterministic fallback always."""
    fallback = _deterministic_summary(plan)
    prompt = (
        "You are an SRE explaining Kubernetes right-sizing recommendations to a CFO in "
        "2-3 sentences. Focus on cost impact and correctness (headroom over observed p99)."
    )
    text = await llm.narrate(prompt, plan.model_dump(mode="json"))
    return plan.model_copy(update={"narration": text or fallback})
