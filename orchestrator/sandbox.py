from pathlib import Path

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / "infra" / ".env"


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    gateway_url: str = "http://127.0.0.1:8080"


async def sandbox_exec(cmd: str, image: str | None = None, timeout_s: int = 30) -> dict:
    settings = GatewaySettings()
    payload: dict[str, object] = {"cmd": cmd, "timeout_s": timeout_s}
    if image:
        payload["image"] = image
    async with httpx.AsyncClient(timeout=timeout_s + 30) as client:
        resp = await client.post(f"{settings.gateway_url}/exec", json=payload)
        resp.raise_for_status()
        return resp.json()
