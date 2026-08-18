import asyncio
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from httpx import HTTPError
from pydantic import BaseModel

from agent import run_agent
from llm import LLMSettings, ask_llm
from sandbox import sandbox_exec

app = FastAPI(title="devin-clone orchestrator", version="0.1.0")


class ExecRequest(BaseModel):
    cmd: str
    image: str | None = None
    timeout_s: int = 30


class AgentRunRequest(BaseModel):
    task: str
    history: list[dict[str, str]] | None = None


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
        return await sandbox_exec(req.cmd, image=req.image, timeout_s=req.timeout_s)
    except HTTPError as e:
        raise HTTPException(status_code=502, detail=f"gateway call failed: {e}")


@app.get("/sandbox/ls")
async def sandbox_ls() -> dict:
    return await sandbox_exec("ls -la /")


@app.post("/agent/run")
async def agent_run(req: AgentRunRequest) -> dict:
    if not req.task.strip():
        raise HTTPException(status_code=422, detail="task must not be empty")
    return await run_agent(req.task, history=req.history)


@app.post("/agent/run/stream")
async def agent_run_stream(req: AgentRunRequest) -> StreamingResponse:
    if not req.task.strip():
        raise HTTPException(status_code=422, detail="task must not be empty")
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def run() -> None:
        try:
            result = await run_agent(
                req.task,
                on_step=lambda step: queue.put_nowait({"event": "step", "data": step}),
                history=req.history,
            )
            queue.put_nowait({"event": "result", "data": result})
        except Exception as e:  # noqa: BLE001 - keep the stream alive and tell the client
            queue.put_nowait({"event": "error", "data": {"error": str(e)}})
        finally:
            queue.put_nowait(None)

    async def gen():
        task = asyncio.create_task(run())
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"event: {item['event']}\ndata: {json.dumps(item['data'])}\n\n"
        await task

    return StreamingResponse(gen(), media_type="text/event-stream")
