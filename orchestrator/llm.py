import asyncio
from pathlib import Path
from typing import Any

import litellm
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / "infra" / ".env"


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
