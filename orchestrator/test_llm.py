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
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "openrouter/free")

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
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "openrouter/free")

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
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "openrouter/free")

    def fake_completion(**kwargs: Any) -> FakeResponse:
        raise RuntimeError("primary down")

    monkeypatch.setattr("llm.litellm.completion", fake_completion)
    with pytest.raises(RuntimeError, match="primary down"):
        llm.chat([{"role": "user", "content": "hi"}])


def test_achat_runs_off_thread(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-primary")
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "openrouter/free")

    def fake_completion(**kwargs: Any) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("llm.litellm.completion", fake_completion)

    async def main() -> dict[str, Any]:
        return await llm.achat([{"role": "user", "content": "hi"}])

    result = asyncio.run(main())
    assert result["content"] == "hi"


def test_ollama_native_path_translates_tool_calls(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("LLM_API_KEY", "ollama")

    captured: dict[str, Any] = {}

    class FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "function": {
                                "name": "bash",
                                "arguments": {"cmd": "ls /"},
                            }
                        }
                    ],
                }
            }

    def fake_post(url: str, json: dict[str, Any], timeout: int) -> FakeResponse:
        captured.update({"url": url, "json": json})
        return FakeResponse()

    monkeypatch.setattr("llm.httpx.post", fake_post)
    result = llm.chat(
        [
            {"role": "user", "content": "list /"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {"name": "bash", "arguments": '{"cmd": "ls /"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "bin boot dev"},
        ]
    )
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    sent = captured["json"]["messages"]
    assert sent[-1] == {"role": "tool", "content": "bin boot dev"}
    assert sent[-2]["tool_calls"][0]["function"]["arguments"] == {"cmd": "ls /"}
    assert result["tool_calls"][0]["function"]["arguments"] == '{"cmd": "ls /"}'
    assert result["tool_calls"][0]["id"] == "call_0"
