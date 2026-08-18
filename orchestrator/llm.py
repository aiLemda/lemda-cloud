import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import litellm
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / "infra" / ".env"

OLLAMA_BASE_URL = "http://127.0.0.1:11434"


def _ollama_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    timeout_s: int,
    model: str,
) -> dict[str, Any]:
    """Talk to a local Ollama server directly.

    litellm's Ollama integration drops tool results, so the model never sees
    command output and re-issues the same tool call forever. Ollama's native
    /api/chat handles the conversation correctly, so we bypass litellm for
    local models.
    """
    ollama_messages: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            ollama_messages.append({"role": "tool", "content": m.get("content") or ""})
            continue
        msg: dict[str, Any] = {"role": role, "content": m.get("content") or ""}
        tool_calls = m.get("tool_calls")
        if tool_calls:
            calls = []
            for tc in tool_calls:
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except (json.JSONDecodeError, KeyError):
                    args = {}
                calls.append(
                    {"function": {"name": tc["function"]["name"], "arguments": args}}
                )
            msg["tool_calls"] = calls
        ollama_messages.append(msg)

    body: dict[str, Any] = {
        "model": model,
        "messages": ollama_messages,
        "stream": False,
    }
    if tools:
        body["tools"] = tools
    resp = httpx.post(f"{OLLAMA_BASE_URL}/api/chat", json=body, timeout=timeout_s)
    resp.raise_for_status()
    message = resp.json()["message"]
    result: dict[str, Any] = {
        "role": "assistant",
        "content": message.get("content") or "",
    }
    tool_calls = message.get("tool_calls")
    if tool_calls:
        result["tool_calls"] = [
            {
                "id": f"call_{i}",
                "type": "function",
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": json.dumps(tc["function"]["arguments"]),
                },
            }
            for i, tc in enumerate(tool_calls)
        ]
    return result


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    llm_provider: str = "openrouter"
    llm_api_key: str = ""
    llm_model: str = "openrouter/free"

    llm_fallback_provider: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_model: str = ""


def _completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    timeout_s: int,
    provider: str,
    api_key: str,
    model: str,
) -> dict[str, Any]:
    if provider == "ollama":
        return _ollama_completion(messages, tools, timeout_s, model)
    kwargs: dict[str, Any] = {
        "model": f"{provider}/{model}",
        "api_key": api_key,
        "messages": messages,
        "timeout": timeout_s,
    }
    if tools:
        kwargs["tools"] = tools
    response = litellm.completion(**kwargs)
    return response.choices[0].message.model_dump()


def ask_llm(prompt: str, timeout_s: int = 120) -> str:
    settings = LLMSettings()
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is empty - fill it in infra/.env")
    response = litellm.completion(
        model=f"{settings.llm_provider}/{settings.llm_model}",
        api_key=settings.llm_api_key,
        messages=[{"role": "user", "content": prompt}],
        timeout=timeout_s,
    )
    return response.choices[0].message.content or ""


def chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    timeout_s: int = 120,
) -> dict[str, Any]:
    settings = LLMSettings()
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is empty - fill it in infra/.env")
    try:
        return _completion(
            messages,
            tools,
            timeout_s,
            settings.llm_provider,
            settings.llm_api_key,
            settings.llm_model,
        )
    except (
        Exception
    ):  # providers throw heterogeneous errors; only fall back when configured
        if settings.llm_fallback_api_key:
            return _completion(
                messages,
                tools,
                timeout_s,
                settings.llm_fallback_provider,
                settings.llm_fallback_api_key,
                settings.llm_fallback_model,
            )
        raise


async def achat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    timeout_s: int = 120,
) -> dict[str, Any]:
    return await asyncio.to_thread(chat, messages, tools, timeout_s)
