from fastapi import FastAPI, HTTPException
from httpx import HTTPError
from pydantic import BaseModel

from llm import LLMSettings, ask_llm
from sandbox import sandbox_exec

app = FastAPI(title="devin-clone orchestrator", version="0.1.0")


class ExecRequest(BaseModel):
    cmd: str
    image: str | None = None
    timeout_s: int = 30


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "orchestrator"}


@app.get("/llm/ping")
def llm_ping() -> dict[str, str]:
    settings = LLMSettings()
    reply = ask_llm("Reply with exactly: ok")
    return {"model": f"{settings.llm_provider}/{settings.llm_model}", "reply": reply}


@app.post("/sandbox/exec")
async def sandbox_exec_endpoint(req: ExecRequest) -> dict:
    try:
        return await sandbox_exec(req.cmd, req.image, req.timeout_s)
    except HTTPError as e:
        raise HTTPException(status_code=502, detail=f"gateway call failed: {e}")


@app.get("/sandbox/ls")
async def sandbox_ls() -> dict:
    return await sandbox_exec("ls -la /")
