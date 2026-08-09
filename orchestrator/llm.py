from pathlib import Path

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
