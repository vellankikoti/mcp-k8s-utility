from __future__ import annotations

import os
from typing import Any

import httpx


class PromClient:
    """Minimal Prometheus HTTP API v1 wrapper. Never raises from query().

    Auth priority (mutually exclusive; first match wins):
    1. PROMETHEUS_BEARER_TOKEN — added as ``Authorization: Bearer <token>``.
    2. PROMETHEUS_USER + PROMETHEUS_PASSWORD — HTTP basic auth.
    3. No auth header.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout_s: float = 10.0,
        bearer_token: str | None = None,
        basic_user: str | None = None,
        basic_password: str | None = None,
    ) -> None:
        self._base = (base_url or os.environ.get("PROMETHEUS_URL") or "").rstrip("/")
        self._timeout = timeout_s

        # Resolve auth from explicit args, then env vars.
        self._bearer = bearer_token or os.environ.get("PROMETHEUS_BEARER_TOKEN") or ""
        self._user = basic_user or os.environ.get("PROMETHEUS_USER") or ""
        self._password = basic_password or os.environ.get("PROMETHEUS_PASSWORD") or ""

    def _auth_headers(self) -> dict[str, str]:
        """Return the appropriate Authorization header dict (may be empty)."""
        if self._bearer:
            return {"Authorization": f"Bearer {self._bearer}"}
        if self._user:
            import base64

            creds = base64.b64encode(f"{self._user}:{self._password}".encode()).decode()
            return {"Authorization": f"Basic {creds}"}
        return {}

    def _basic_auth(self) -> tuple[str, str] | None:
        """Return (user, password) tuple for httpx basic_auth if bearer is not set."""
        if self._bearer:
            return None
        if self._user:
            return (self._user, self._password)
        return None

    @property
    def configured(self) -> bool:
        return bool(self._base)

    async def instant(self, expr: str) -> list[dict[str, Any]]:
        """Return []-safe response from /api/v1/query. Returns [] on any error."""
        if not self._base:
            return []
        try:
            headers = self._auth_headers()
            async with httpx.AsyncClient(timeout=self._timeout, headers=headers) as client:
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
