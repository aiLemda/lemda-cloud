import asyncio
from typing import Any

import pytest

import llm


class FakeMessage:
    def model_dump(self) -> dict[str, Any]:
        return {"role": "assistant", "content": "hi", "tool_calls": None}


class FakeResponse:
    def __init__(self) -> None:
        self.choices = [type("C", (), {"message": FakeMessage()})()]


def test_chat_uses_primary(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setenv("LLM_API_KEY", "sk-primary")
    monkeypatch.setenv("LLM_FALLBACK_API_KEY", "sk-fallback")

    def fake_completion(**kwargs: Any) -> FakeResponse:
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("llm.litellm.completion", fake_completion)
    result = llm.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])
    assert result["content"] == "hi"
    assert captured["model"] == "openrouter/openrouter/free"
    assert captured["api_key"] == "sk-primary"
    assert "tools" in captured


def test_chat_falls_back_when_primary_fails(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setenv("LLM_API_KEY", "sk-primary")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "gemini")
    monkeypatch.setenv("LLM_FALLBACK_API_KEY", "sk-fallback")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "gemini-2.5-flash")

    def fake_completion(**kwargs: Any) -> FakeResponse:
        calls.append(kwargs["model"])
        if kwargs["api_key"] == "sk-primary":
            raise RuntimeError("primary down")
        return FakeResponse()

    monkeypatch.setattr("llm.litellm.completion", fake_completion)
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result["content"] == "hi"
    assert calls == ["openrouter/openrouter/free", "gemini/gemini-2.5-flash"]


def test_chat_raises_without_fallback(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-primary")
    monkeypatch.setenv("LLM_FALLBACK_API_KEY", "")

    def fake_completion(**kwargs: Any) -> FakeResponse:
        raise RuntimeError("primary down")

    monkeypatch.setattr("llm.litellm.completion", fake_completion)
    with pytest.raises(RuntimeError, match="primary down"):
        llm.chat([{"role": "user", "content": "hi"}])


def test_achat_runs_off_thread(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-primary")

    def fake_completion(**kwargs: Any) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("llm.litellm.completion", fake_completion)

    async def main() -> dict[str, Any]:
        return await llm.achat([{"role": "user", "content": "hi"}])

    result = asyncio.run(main())
    assert result["content"] == "hi"
