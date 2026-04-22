from __future__ import annotations

import fnmatch
from datetime import UTC, datetime
from typing import Any

from utility_server.models import OpenSearchIndexSummary
from utility_server.opensearch_client import OpenSearchClient


def _parse_creation(value: Any) -> datetime | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _retention_tagged(settings: dict[str, Any]) -> bool:
    """True if the index has any known retention / compliance / legal-hold marker."""
    for root_key, root_val in settings.items():
        if not isinstance(root_val, dict):
            continue
        idx = root_val.get("settings", {}).get("index", {})
        meta = idx.get("meta") or idx.get("_meta") or {}
        if isinstance(meta, dict):
            for tag_key in ("retention", "compliance", "legal_hold", "legal-hold"):
                if tag_key in meta:
                    return True
        for lifecycle_key in ("lifecycle", "plugins", "retention_policy_id"):
            val = idx.get(lifecycle_key)
            if isinstance(val, dict) and val.get("name"):
                return True
            if isinstance(val, str) and val:
                return True
        _ = root_key
    return False


def _pattern_match(name: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        if fnmatch.fnmatch(name, pat):
            return pat
    return None


async def list_old_indices(
    *,
    client: OpenSearchClient,
    older_than_days: float,
    index_patterns: list[str],
    now: datetime | None = None,
) -> list[OpenSearchIndexSummary]:
    if not index_patterns:
        return []
    moment = now or datetime.now(UTC)
    raw = await client.list_indices()
    out: list[OpenSearchIndexSummary] = []
    for row in raw:
        name = str(row.get("index") or "")
        matched = _pattern_match(name, index_patterns)
        if not matched:
            continue
        created = _parse_creation(row.get("creation.date.string"))
        age_days = None
        if created is not None:
            age_days = round((moment - created).total_seconds() / 86400.0, 2)
        if age_days is None or age_days < older_than_days:
            continue
        try:
            size_bytes = int(row.get("store.size") or 0)
        except (TypeError, ValueError):
            size_bytes = 0
        try:
            doc_count = int(row.get("docs.count") or 0)
        except (TypeError, ValueError):
            doc_count = 0
        settings = await client.get_index_settings(name)
        out.append(
            OpenSearchIndexSummary(
                name=name,
                doc_count=doc_count,
                size_bytes=size_bytes,
                creation_timestamp=created,
                age_days=age_days,
                retention_tagged=_retention_tagged(settings),
                matched_pattern=matched,
            )
        )
    out.sort(key=lambda i: i.age_days or 0, reverse=True)
    return out
