import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from httpx import HTTPError
from pydantic import BaseModel

from agent import run_agent
from conversations import ConversationStore
from llm import LLMSettings, ask_llm
from sandbox import sandbox_exec

CONVERSATION_TTL_SECS = float(os.getenv("CONVERSATION_TTL_SECS", "3600"))
CONVERSATION_REAP_INTERVAL_SECS = float(
    os.getenv("CONVERSATION_REAP_INTERVAL_SECS", "60")
)

conversations = ConversationStore(
    ttl_secs=CONVERSATION_TTL_SECS,
    reap_interval_secs=CONVERSATION_REAP_INTERVAL_SECS,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Evict idle conversations on a background loop, like the gateway's
    session reaper."""

    async def reaper_loop() -> None:
        while True:
            await asyncio.sleep(conversations.reap_interval)
            conversations.reap_expired()

    task = asyncio.create_task(reaper_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="devin-clone orchestrator", version="0.1.0", lifespan=lifespan)


class ExecRequest(BaseModel):
    cmd: str
    image: str | None = None
    timeout_s: int = 30


class AgentRunRequest(BaseModel):
    task: str
    history: list[dict[str, str]] | None = None


class ConversationMessageRequest(BaseModel):
    role: Literal["user", "assistant"]
    content: str


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


@app.post("/conversations", status_code=201)
def create_conversation() -> dict:
    return conversations.create()


@app.get("/conversations")
def list_conversations() -> list[dict]:
    return conversations.list()


@app.get("/conversations/{cid}")
def get_conversation(cid: str) -> dict:
    conv = conversations.get(cid)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conv


@app.post("/conversations/{cid}/messages")
def append_conversation_message(cid: str, req: ConversationMessageRequest) -> dict:
    conv = conversations.append(cid, req.role, req.content)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conv


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

    def emit_answer_token(delta: str) -> None:
        queue.put_nowait({"event": "answer_token", "data": {"delta": delta}})

    async def run() -> None:
        try:
            result = await run_agent(
                req.task,
                on_step=lambda step: queue.put_nowait({"event": "step", "data": step}),
                history=req.history,
                on_answer_token=emit_answer_token,
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
