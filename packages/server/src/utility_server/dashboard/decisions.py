from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any

import aiosqlite


async def load_opa_summary(limit: int = 100) -> dict[str, Any]:
    """Aggregate recent audit rows by status; extract top denials."""
    path = os.environ.get("SECUREOPS_AUDIT_DB", "")
    default: dict[str, Any] = {
        "status_counts": {},
        "total": 0,
        "denials": [],
        "audit_path": path,
    }
    if not path or not os.path.exists(path):
        return default

    status_counts: Counter[str] = Counter()
    denials: list[dict[str, Any]] = []
    total = 0
    try:
        async with (
            aiosqlite.connect(path) as conn,
            conn.execute(
                "SELECT row_id, action_id, payload_json, created_at "
                "FROM audit_rows ORDER BY row_id DESC LIMIT ?",
                (limit,),
            ) as cur,
        ):
            async for row_id, action_id, payload_json, created_at in cur:
                total += 1
                try:
                    payload = json.loads(payload_json)
                except json.JSONDecodeError:
                    continue
                result = payload.get("result") or {}
                status = result.get("status") or "unknown"
                status_counts[str(status)] += 1
                if str(status).startswith("denied_") and len(denials) < 5:
                    opa = result.get("opa_decision") or {}
                    reasons = opa.get("reasons") or []
                    proposal = payload.get("proposal") or {}
                    denials.append(
                        {
                            "row_id": row_id,
                            "action_id": action_id,
                            "created_at": created_at,
                            "tool": proposal.get("tool_name"),
                            "status": status,
                            "reasons": list(reasons) if isinstance(reasons, list) else [],
                        }
                    )
    except Exception:
        return default

    return {
        "status_counts": dict(status_counts),
        "total": total,
        "denials": denials,
        "audit_path": path,
    }
