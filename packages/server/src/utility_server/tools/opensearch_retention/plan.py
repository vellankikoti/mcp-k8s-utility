from __future__ import annotations

from datetime import UTC, datetime

from utility_server.llm.adapter import UtilityLLM
from utility_server.models import (
    OpenSearchIndexSummary,
    RetentionCleanupCandidate,
    RetentionCleanupPlan,
)
from utility_server.opensearch_client import OpenSearchClient
from utility_server.tools.opensearch_retention.scan import list_old_indices

_DEFAULT_MAX_DELETES = 50


def _format_bytes(n: int) -> str:
    step = 1024.0
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if n < step:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n = int(n / step)
    return f"{n:.1f} EiB"


def _build_candidates(
    indices: list[OpenSearchIndexSummary], max_deletes: int
) -> list[RetentionCleanupCandidate]:
    out: list[RetentionCleanupCandidate] = []
    approved = 0
    for idx in indices:
        if idx.retention_tagged:
            out.append(
                RetentionCleanupCandidate(
                    index=idx,
                    will_delete=False,
                    skip_reason="index carries a retention / compliance tag",
                )
            )
            continue
        if approved >= max_deletes:
            out.append(
                RetentionCleanupCandidate(
                    index=idx,
                    will_delete=False,
                    skip_reason=f"rate limit reached ({max_deletes} per call)",
                )
            )
            continue
        out.append(RetentionCleanupCandidate(index=idx, will_delete=True, skip_reason=None))
        approved += 1
    return out


def _deterministic_summary(plan_total_bytes: int, plan_total_docs: int, n_delete: int) -> str:
    if n_delete == 0:
        return "No OpenSearch indices eligible for retention cleanup at this time."
    return (
        f"Retention cleanup would remove {n_delete} index(es), reclaiming "
        f"{_format_bytes(plan_total_bytes)} and {plan_total_docs:,} documents. "
        "Dry-run by default; explicit confirmation required to apply."
    )


async def propose_retention_plan(
    *,
    client: OpenSearchClient,
    older_than_days: float,
    index_patterns: list[str],
    max_deletes: int = _DEFAULT_MAX_DELETES,
    llm: UtilityLLM | None = None,
    now: datetime | None = None,
) -> RetentionCleanupPlan:
    moment = now or datetime.now(UTC)
    indices = await list_old_indices(
        client=client,
        older_than_days=older_than_days,
        index_patterns=index_patterns,
        now=moment,
    )
    candidates = _build_candidates(indices, max_deletes=max_deletes)

    will_delete = [c for c in candidates if c.will_delete]
    total_bytes = sum(c.index.size_bytes for c in will_delete)
    total_docs = sum(c.index.doc_count for c in will_delete)

    fallback = _deterministic_summary(total_bytes, total_docs, len(will_delete))
    narration = fallback
    if llm is not None:
        provider_out = await llm.narrate(
            "Summarise this OpenSearch retention cleanup plan for a CFO in 2 sentences. "
            "Focus on reclaimed bytes and that nothing is deleted by default.",
            {
                "older_than_days": older_than_days,
                "index_patterns": index_patterns,
                "total_bytes_to_reclaim": total_bytes,
                "total_docs_to_remove": total_docs,
                "n_candidates": len(candidates),
                "n_to_delete": len(will_delete),
            },
        )
        if provider_out:
            narration = provider_out

    return RetentionCleanupPlan(
        older_than_days=older_than_days,
        index_patterns=list(index_patterns),
        max_deletes=max_deletes,
        candidates=candidates,
        total_bytes_to_reclaim=total_bytes,
        total_docs_to_remove=total_docs,
        narration=narration,
        proposed_at=moment,
    )
