from __future__ import annotations

import os
from typing import Any

import httpx


class PromClient:
    """Minimal Prometheus HTTP API v1 wrapper. Never raises from query()."""

    def __init__(self, base_url: str | None = None, timeout_s: float = 10.0) -> None:
        self._base = (base_url or os.environ.get("PROMETHEUS_URL") or "").rstrip("/")
        self._timeout = timeout_s

    @property
    def configured(self) -> bool:
        return bool(self._base)

    async def instant(self, expr: str) -> list[dict[str, Any]]:
        """Return []-safe response from /api/v1/query. Returns [] on any error."""
        if not self._base:
            return []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(f"{self._base}/api/v1/query", params={"query": expr})
                r.raise_for_status()
                data = r.json()
            if data.get("status") != "success":
                return []
            result = data.get("data", {}).get("result", [])
            return list(result) if isinstance(result, list) else []
        except Exception:
            return []

    @staticmethod
    def first_value(result: list[dict[str, Any]], default: float = 0.0) -> float:
        if not result:
            return default
        val = result[0].get("value")
        if not val or len(val) < 2:
            return default
        try:
            return float(val[1])
        except (TypeError, ValueError):
            return default
