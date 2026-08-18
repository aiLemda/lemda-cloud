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


async def sandbox_exec(
    cmd: str,
    session_id: str | None = None,
    image: str | None = None,
    timeout_s: int = 30,
) -> dict:
    settings = GatewaySettings()
    payload: dict[str, object] = {"cmd": cmd, "timeout_s": timeout_s}
    if image:
        payload["image"] = image
    url = (
        f"{settings.gateway_url}/sessions/{session_id}/exec"
        if session_id
        else f"{settings.gateway_url}/exec"
    )
    async with httpx.AsyncClient(timeout=timeout_s + 30) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


async def sandbox_create_session(image: str | None = None) -> str:
    settings = GatewaySettings()
    payload: dict[str, object] = {}
    if image:
        payload["image"] = image
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{settings.gateway_url}/sessions", json=payload)
        resp.raise_for_status()
        return resp.json()["session_id"]


async def sandbox_close_session(session_id: str) -> None:
    settings = GatewaySettings()
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.delete(f"{settings.gateway_url}/sessions/{session_id}")
        resp.raise_for_status()
