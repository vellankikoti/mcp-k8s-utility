from __future__ import annotations

import json
import os
from enum import StrEnum
from typing import Any


class Provider(StrEnum):
    VERTEX = "vertex"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    DISABLED = "disabled"


class UtilityLLM:
    """Pluggable LLM narrator that never raises.

    `narrate(prompt, structured)` returns a string on success or None on any
    failure (provider missing, SDK not installed, timeout, API error).
    Callers always pair it with a deterministic fallback so the tool
    behaves identically with or without the LLM.
    """

    def __init__(self, provider: Provider | None = None) -> None:
        self._provider: Provider = provider or Provider.DISABLED

    @classmethod
    def from_env(cls) -> UtilityLLM:
        raw = os.environ.get("UTILITY_LLM_PROVIDER", "").strip().lower()
        if not raw:
            return cls(Provider.DISABLED)
        try:
            return cls(Provider(raw))
        except ValueError as e:
            raise ValueError(
                f"UTILITY_LLM_PROVIDER={raw!r} is not recognized; "
                f"valid values: {', '.join(p.value for p in Provider)}"
            ) from e

    @property
    def provider_name(self) -> str:
        return self._provider.value

    async def narrate(self, prompt: str, structured: dict[str, Any]) -> str | None:
        if self._provider is Provider.DISABLED:
            return None
        try:
            if self._provider is Provider.VERTEX:
                return await _narrate_vertex(prompt, structured)
            if self._provider is Provider.ANTHROPIC:
                return await _narrate_anthropic(prompt, structured)
            if self._provider is Provider.OPENAI:
                return await _narrate_openai(prompt, structured)
            if self._provider is Provider.OLLAMA:
                return await _narrate_ollama(prompt, structured)
        except Exception:
            return None
        return None


def _compose_user_message(prompt: str, structured: dict[str, Any]) -> str:
    return f"{prompt}\n\nStructured context:\n```json\n{json.dumps(structured, default=str)}\n```"


def _model_for(provider: Provider, default: str) -> str:
    return os.environ.get("UTILITY_LLM_MODEL", default)


async def _narrate_vertex(prompt: str, structured: dict[str, Any]) -> str | None:
    try:
        import vertexai  # type: ignore[import-not-found,unused-ignore]
        from vertexai.generative_models import (
            GenerativeModel,  # type: ignore[import-not-found,unused-ignore]
        )
    except ImportError:
        return None

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    if project:
        vertexai.init(project=project, location=location)
    model_name = _model_for(Provider.VERTEX, "gemini-2.5-flash")
    model = GenerativeModel(model_name)
    content = _compose_user_message(prompt, structured)
    resp = await model.generate_content_async(content)
    text = getattr(resp, "text", None)
    return str(text) if text else None


async def _narrate_anthropic(prompt: str, structured: dict[str, Any]) -> str | None:
    try:
        from anthropic import AsyncAnthropic  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        return None

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    client = AsyncAnthropic()
    model_name = _model_for(Provider.ANTHROPIC, "claude-sonnet-4-5")
    resp = await client.messages.create(
        model=model_name,
        max_tokens=400,
        messages=[{"role": "user", "content": _compose_user_message(prompt, structured)}],
    )
    blocks = getattr(resp, "content", None) or []
    for block in blocks:
        text = getattr(block, "text", None)
        if text:
            return str(text)
    return None


async def _narrate_openai(prompt: str, structured: dict[str, Any]) -> str | None:
    try:
        from openai import AsyncOpenAI  # type: ignore[import-not-found,unused-ignore]
    except ImportError:
        return None

    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("OPENAI_BASE_URL"):
        return None
    client = AsyncOpenAI()
    model_name = _model_for(Provider.OPENAI, "gpt-4o-mini")
    resp = await client.chat.completions.create(
        model=model_name,
        max_tokens=400,
        messages=[{"role": "user", "content": _compose_user_message(prompt, structured)}],
    )
    choices = getattr(resp, "choices", None) or []
    if not choices:
        return None
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    return str(content) if content else None


async def _narrate_ollama(prompt: str, structured: dict[str, Any]) -> str | None:
    import httpx

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model_name = _model_for(Provider.OLLAMA, "llama3.2")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{host}/api/generate",
            json={
                "model": model_name,
                "prompt": _compose_user_message(prompt, structured),
                "stream": False,
            },
        )
        r.raise_for_status()
        data = r.json()
        text = data.get("response")
        return str(text) if text else None
