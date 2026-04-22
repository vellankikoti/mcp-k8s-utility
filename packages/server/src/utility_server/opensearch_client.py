from __future__ import annotations

import os
from typing import Any

import httpx


class OpenSearchClient:
    """Minimal OpenSearch/Elasticsearch-compatible HTTP wrapper. Never raises."""

    def __init__(
        self,
        base_url: str | None = None,
        user: str | None = None,
        password: str | None = None,
        api_key: str | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        self._base = (base_url or os.environ.get("OPENSEARCH_URL") or "").rstrip("/")
        self._user = user if user is not None else os.environ.get("OPENSEARCH_USER")
        self._password = password if password is not None else os.environ.get("OPENSEARCH_PASSWORD")
        self._api_key = api_key if api_key is not None else os.environ.get("OPENSEARCH_API_KEY")
        self._timeout = timeout_s

    @property
    def configured(self) -> bool:
        return bool(self._base)

    def _auth_and_headers(self) -> tuple[tuple[str, str] | None, dict[str, str]]:
        headers = {"accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"ApiKey {self._api_key}"
            return None, headers
        if self._user and self._password:
            return (self._user, self._password), headers
        return None, headers

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response | None:
        if not self._base:
            return None
        auth, headers = self._auth_and_headers()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.request(
                    method, f"{self._base}{path}", auth=auth, headers=headers, **kwargs
                )
                r.raise_for_status()
                return r
        except Exception:
            return None

    async def list_indices(self) -> list[dict[str, Any]]:
        """GET /_cat/indices in JSON, bytes as raw integers."""
        r = await self._request(
            "GET",
            "/_cat/indices",
            params={
                "format": "json",
                "bytes": "b",
                "h": "index,docs.count,store.size,creation.date.string",
            },
        )
        if r is None:
            return []
        try:
            data = r.json()
            return list(data) if isinstance(data, list) else []
        except Exception:
            return []

    async def get_index_settings(self, index: str) -> dict[str, Any]:
        """GET /{index}/_settings. Returns {} on any failure."""
        r = await self._request("GET", f"/{index}/_settings")
        if r is None:
            return {}
        try:
            data = r.json()
            return dict(data) if isinstance(data, dict) else {}
        except Exception:
            return {}

    async def delete_index(self, index: str) -> bool:
        """DELETE /{index}. Returns True on success, False otherwise."""
        r = await self._request("DELETE", f"/{index}")
        return r is not None
