"""Tests for PromClient bearer token and basic auth.

Uses pytest-httpx to intercept outgoing HTTP requests and assert the
Authorization header is set correctly in each auth mode.
"""

from __future__ import annotations

import base64

import pytest
from pytest_httpx import HTTPXMock
from utility_server.prom_client import PromClient

_PROM_URL = "http://prometheus.example.com:9090"

_SUCCESS_BODY = {
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [{"metric": {}, "value": [1714000000, "42"]}],
    },
}


@pytest.fixture()
def prom_url() -> str:
    return _PROM_URL


async def test_no_auth_sends_no_authorization_header(httpx_mock: HTTPXMock, prom_url: str) -> None:
    httpx_mock.add_response(json=_SUCCESS_BODY)
    client = PromClient(base_url=prom_url)
    await client.instant("up")

    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert "authorization" not in {k.lower() for k in requests[0].headers}


async def test_bearer_token_arg_sets_header(httpx_mock: HTTPXMock, prom_url: str) -> None:
    httpx_mock.add_response(json=_SUCCESS_BODY)
    client = PromClient(base_url=prom_url, bearer_token="my-secret-token")
    await client.instant("up")

    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert requests[0].headers["authorization"] == "Bearer my-secret-token"


async def test_bearer_token_env_sets_header(
    httpx_mock: HTTPXMock, prom_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROMETHEUS_BEARER_TOKEN", "env-token-abc")
    monkeypatch.delenv("PROMETHEUS_USER", raising=False)
    monkeypatch.delenv("PROMETHEUS_PASSWORD", raising=False)
    httpx_mock.add_response(json=_SUCCESS_BODY)
    client = PromClient(base_url=prom_url)
    await client.instant("up")

    requests = httpx_mock.get_requests()
    assert requests[0].headers["authorization"] == "Bearer env-token-abc"


async def test_basic_auth_arg_sets_header(httpx_mock: HTTPXMock, prom_url: str) -> None:
    httpx_mock.add_response(json=_SUCCESS_BODY)
    client = PromClient(base_url=prom_url, basic_user="alice", basic_password="s3cr3t")
    await client.instant("up")

    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    auth_header = requests[0].headers["authorization"]
    assert auth_header.startswith("Basic ")
    decoded = base64.b64decode(auth_header[6:]).decode()
    assert decoded == "alice:s3cr3t"


async def test_basic_auth_env_sets_header(
    httpx_mock: HTTPXMock, prom_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PROMETHEUS_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("PROMETHEUS_USER", "bob")
    monkeypatch.setenv("PROMETHEUS_PASSWORD", "p@ss!")
    httpx_mock.add_response(json=_SUCCESS_BODY)
    client = PromClient(base_url=prom_url)
    await client.instant("up")

    requests = httpx_mock.get_requests()
    auth_header = requests[0].headers["authorization"]
    assert auth_header.startswith("Basic ")
    decoded = base64.b64decode(auth_header[6:]).decode()
    assert decoded == "bob:p@ss!"


async def test_bearer_takes_priority_over_basic(httpx_mock: HTTPXMock, prom_url: str) -> None:
    """When both bearer and basic are set, bearer wins."""
    httpx_mock.add_response(json=_SUCCESS_BODY)
    client = PromClient(
        base_url=prom_url,
        bearer_token="token-wins",
        basic_user="alice",
        basic_password="ignored",
    )
    await client.instant("up")

    requests = httpx_mock.get_requests()
    auth_header = requests[0].headers["authorization"]
    assert auth_header == "Bearer token-wins"


async def test_unconfigured_client_returns_empty_without_request(
    httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PROMETHEUS_URL", raising=False)
    client = PromClient()
    assert not client.configured

    result = await client.instant("up")
    assert result == []
    assert httpx_mock.get_requests() == []
