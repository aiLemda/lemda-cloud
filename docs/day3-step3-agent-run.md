# Day 3 — Step 3: Expose the loop to the world (`orchestrator/main.py`)

## Topic

The agent loop (`agent.py`) was a library function. This step gives it a door:
`POST /agent/run` on the orchestrator API. Anyone can now send a task and get
back the full trace of the agent's thinking + the final answer.

## What I did

1. **Imported the loop** (`main.py:5`): `from agent import run_agent`.
2. **Request model** (`main.py:18-19`): `AgentRunRequest` with a single `task`
   field, validated by Pydantic.
3. **The endpoint** (`main.py:47-51`):
   - Empty/whitespace task → HTTP `422` (fail fast, no LLM call wasted).
   - Otherwise `await run_agent(req.task)` → returns the loop's dict directly:
     `{ok, answer, steps}` (or `{ok: false, error, steps}` on failure).
4. **API tests** (`test_agent_api.py`, new file):
   - `test_agent_run_wiring` — monkeypatches `main.run_agent` (the name bound
     in main's namespace, not the source module) so no network is touched;
     asserts 200 + `ok`/`answer`/`steps` shape.
   - `test_agent_run_rejects_empty_task` — asserts 422 + message.
5. **Fixed the environment** for the live demo: the Rust sandbox-gateway
   (port 8080) was built but not running — the first demo attempt failed with
   `httpx.ConnectError` at the gateway. Restarted the prebuilt binary
   (`sandbox-gateway/target/debug/sandbox-gateway`).

## Why

- **Traceability by design:** the response keeps every `steps[]` entry —
  each tool call, its command, and the raw sandbox output. That's the seed of
  Day 45's observability (replay "what did the agent do?"): today it's just
  JSON in an HTTP response, later it becomes stored sessions + live streams.
- **The demo proved the whole stack:** HTTP → FastAPI → agent loop → LiteLLM
  → real model → real tool call → Docker sandbox → extracted `<answer>`.

## What change it brings

- `curl -X POST localhost:8000/agent/run -H 'Content-Type: application/json' -d '{"task": "..."}'`
  now drives the full agent. Response example (real run):

```json
{
  "ok": true,
  "answer": "The directories in the root directory (`/`) are: bin, boot, dev, ...",
  "steps": [
    {
      "type": "tool",
      "cmd": "ls -la /",
      "result": { "exit_code": 0, "stdout": "total 56\ndrwxr-xr-x ...", "duration_ms": 3746 }
    }
  ]
}
```

- Bad input is rejected with 422 before any API calls are spent.

## Where (file → lines)

| File | Lines | Change |
|---|---|---|
| `orchestrator/main.py` | 5 | import `run_agent` |
| `orchestrator/main.py` | 18-19 | `AgentRunRequest` model |
| `orchestrator/main.py` | 47-51 | `POST /agent/run` endpoint (422 guard + call) |
| `orchestrator/test_agent_api.py` | 1-29 | new file, 2 offline API tests |

Verified: `ruff` clean, `mypy` clean, `pytest` **13 passed**, plus a live
end-to-end run over real HTTP (server on :8010, real LLM, real Docker sandbox —
1 tool step, answer with directory list).
