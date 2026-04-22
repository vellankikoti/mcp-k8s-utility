from __future__ import annotations

import json
import os
from typing import Any

import aiosqlite


async def load_recent_tool_calls(limit: int = 20) -> list[dict[str, Any]]:
    """Read the last N audit rows from the secure-ops ledger. Empty list on any failure."""
    path = os.environ.get("SECUREOPS_AUDIT_DB", "")
    if not path or not os.path.exists(path):
        return []
    rows: list[dict[str, Any]] = []
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
                try:
                    payload = json.loads(payload_json)
                except json.JSONDecodeError:
                    continue
                result = payload.get("result", {}) or {}
                proposal = payload.get("proposal", {}) or {}
                rows.append(
                    {
                        "row_id": row_id,
                        "action_id": action_id,
                        "tool": proposal.get("tool_name"),
                        "status": result.get("status"),
                        "opa_allow": (result.get("opa_decision") or {}).get("allow"),
                        "created_at": created_at,
                    }
                )
    except Exception:
        return []
    return rows
