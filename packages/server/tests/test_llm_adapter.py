from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_httpx import HTTPXMock
from utility_server.llm.adapter import Provider, UtilityLLM

# ── from_env resolution ───────────────────────────────────────────────────────


def test_from_env_defaults_to_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UTILITY_LLM_PROVIDER", raising=False)
    llm = UtilityLLM.from_env()
    assert llm.provider_name == "disabled"


def test_from_env_resolves_lowercase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UTILITY_LLM_PROVIDER", "Anthropic")
    llm = UtilityLLM.from_env()
    assert llm.provider_name == "anthropic"


def test_from_env_rejects_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UTILITY_LLM_PROVIDER", "bogus")
    with pytest.raises(ValueError, match="UTILITY_LLM_PROVIDER"):
        UtilityLLM.from_env()


# ── disabled provider ─────────────────────────────────────────────────────────


async def test_disabled_returns_none() -> None:
    llm = UtilityLLM(Provider.DISABLED)
    assert await llm.narrate("hi", {}) is None


# ── ollama via pytest-httpx ───────────────────────────────────────────────────


async def test_ollama_success(httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("UTILITY_LLM_MODEL", "llama3.2")
    httpx_mock.add_response(
        url="http://localhost:11434/api/generate",
        method="POST",
        json={"response": "hello from ollama"},
    )
    llm = UtilityLLM(Provider.OLLAMA)
    out = await llm.narrate("hi", {"k": "v"})
    assert out == "hello from ollama"


async def test_ollama_unreachable_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # Impossible host ensures a connection error
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:1")
    llm = UtilityLLM(Provider.OLLAMA)
    out = await llm.narrate("hi", {})
    assert out is None


# ── anthropic via injected fake SDK ───────────────────────────────────────────


def _install_fake_anthropic(
    monkeypatch: pytest.MonkeyPatch,
    response_text: str | None,
    raise_exc: Exception | None = None,
) -> None:
    fake_mod = types.ModuleType("anthropic")

    class _FakeAsyncAnthropic:
        def __init__(self, **_: Any) -> None:
            self.messages = MagicMock()
            if raise_exc is not None:
                self.messages.create = AsyncMock(side_effect=raise_exc)
            else:
                block = MagicMock()
                block.text = response_text
                resp = MagicMock()
                resp.content = [block] if response_text is not None else []
                self.messages.create = AsyncMock(return_value=resp)

    fake_mod.AsyncAnthropic = _FakeAsyncAnthropic  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)


async def test_anthropic_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    _install_fake_anthropic(monkeypatch, response_text="hi from claude")
    llm = UtilityLLM(Provider.ANTHROPIC)
    assert await llm.narrate("hi", {}) == "hi from claude"


async def test_anthropic_without_key_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _install_fake_anthropic(monkeypatch, response_text="never called")
    llm = UtilityLLM(Provider.ANTHROPIC)
    assert await llm.narrate("hi", {}) is None


async def test_anthropic_api_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    _install_fake_anthropic(monkeypatch, response_text=None, raise_exc=RuntimeError("boom"))
    llm = UtilityLLM(Provider.ANTHROPIC)
    assert await llm.narrate("hi", {}) is None


async def test_anthropic_missing_sdk_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    monkeypatch.setitem(sys.modules, "anthropic", None)  # type: ignore[arg-type]
    llm = UtilityLLM(Provider.ANTHROPIC)
    assert await llm.narrate("hi", {}) is None


# ── openai via injected fake SDK ──────────────────────────────────────────────


def _install_fake_openai(
    monkeypatch: pytest.MonkeyPatch,
    response_text: str | None,
    raise_exc: Exception | None = None,
) -> None:
    fake_mod = types.ModuleType("openai")

    class _FakeAsyncOpenAI:
        def __init__(self, **_: Any) -> None:
            completions = MagicMock()
            if raise_exc is not None:
                completions.create = AsyncMock(side_effect=raise_exc)
            else:
                message = MagicMock()
                message.content = response_text
                choice = MagicMock()
                choice.message = message
                resp = MagicMock()
                resp.choices = [choice] if response_text is not None else []
                completions.create = AsyncMock(return_value=resp)
            chat = MagicMock()
            chat.completions = completions
            self.chat = chat

    fake_mod.AsyncOpenAI = _FakeAsyncOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", fake_mod)


async def test_openai_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    _install_fake_openai(monkeypatch, response_text="hi from gpt")
    llm = UtilityLLM(Provider.OPENAI)
    assert await llm.narrate("hi", {}) == "hi from gpt"


async def test_openai_without_creds_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    _install_fake_openai(monkeypatch, response_text="never called")
    llm = UtilityLLM(Provider.OPENAI)
    assert await llm.narrate("hi", {}) is None


async def test_openai_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    _install_fake_openai(monkeypatch, response_text=None, raise_exc=RuntimeError("boom"))
    llm = UtilityLLM(Provider.OPENAI)
    assert await llm.narrate("hi", {}) is None


# ── vertex via injected fake SDK ──────────────────────────────────────────────


def _install_fake_vertex(
    monkeypatch: pytest.MonkeyPatch,
    response_text: str | None,
    raise_exc: Exception | None = None,
) -> None:
    vertexai_mod = types.ModuleType("vertexai")
    vertexai_mod.init = MagicMock()  # type: ignore[attr-defined]

    gen_mod = types.ModuleType("vertexai.generative_models")

    class _FakeGenerativeModel:
        def __init__(self, name: str) -> None:
            self._name = name
            if raise_exc is not None:
                self.generate_content_async = AsyncMock(side_effect=raise_exc)
            else:
                resp = MagicMock()
                resp.text = response_text
                self.generate_content_async = AsyncMock(return_value=resp)

    gen_mod.GenerativeModel = _FakeGenerativeModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vertexai", vertexai_mod)
    monkeypatch.setitem(sys.modules, "vertexai.generative_models", gen_mod)


async def test_vertex_returns_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-proj")
    _install_fake_vertex(monkeypatch, response_text="hi from gemini")
    llm = UtilityLLM(Provider.VERTEX)
    assert await llm.narrate("hi", {}) == "hi from gemini"


async def test_vertex_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-proj")
    _install_fake_vertex(monkeypatch, response_text=None, raise_exc=RuntimeError("boom"))
    llm = UtilityLLM(Provider.VERTEX)
    assert await llm.narrate("hi", {}) is None
