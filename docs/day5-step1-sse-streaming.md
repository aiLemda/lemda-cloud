# Day 5 - Step 1: Live streaming (SSE) - watch the robot think

## Goal

Users watch the agent work in real time: every tool step appears in the chat as it happens, instead of appearing only when the whole run finishes.

## Problem

`POST /agent/run` only returns when the run is over. A slow task shows one thinking bubble for 30-60s with zero feedback. No way to tell if the agent is stuck or making progress.

## Solution: Server-Sent Events (SSE)

Same HTTP connection, but the server pushes `event:`/`data:` frames as steps complete.

```
event: step
data: {"type":"tool","cmd":"ls -la /","result":{...}}

event: result
data: {"ok":true,"answer":"...","steps":[...]}
```

### Backend

1. `orchestrator/agent.py`
   - `run_agent()` gains an optional `on_step: Callable[[dict], None]` parameter (`agent.py:48-56`).
   - After every tool step is appended to the diary, `on_step` fires with the same step dict - both the function-call path (`agent.py:83-84`) and the `<bash>` fallback path (`agent.py:98-99`).
   - Non-streaming callers are untouched: `on_step` defaults to `None`.

2. `orchestrator/main.py`
   - New `POST /agent/run/stream` (`main.py:58-84`): an `asyncio.Queue` feeds a background `run()` task; the SSE generator drains the queue and yields frames until a `None` sentinel.
   - Events: `step` (one per tool call, as they happen), `result` (final `{ok, answer, steps}`), `error` (exception keeps the stream alive so the client sees a clean error instead of a dead socket).
   - Empty-task validation matches `/agent/run` (422).

### Frontend

3. `frontend/src/index.ts` - bridge route `/api/agent/run/stream` passes the request to the orchestrator and pipes the response body straight back with `content-type: text/event-stream` + `no-cache` headers.

4. `frontend/src/lib/client.ts` - `streamAgent(task, onStep)`:
   - reads the response body with `getReader()` + `TextDecoder`,
   - splits frames on blank lines, parses `event:`/`data:` lines,
   - pushes each `step` into an accumulating list AND calls `onStep` immediately (UI updates live),
   - resolves with the `result` payload, or a clean error object for `error`/network/server failures.

5. `frontend/src/lib/use-chat.ts` - `submit()` now calls `streamAgent` and appends each arriving step to `steps` state, so the diary grows while the robot works.

6. `frontend/src/App.tsx`
   - While `running`: diary (`TraceViewer`) renders above the thinking bubble whenever at least one step has arrived, and grows live.
   - Auto-scroll effect now also watches `steps`, so the page follows the diary as it grows.

## LLM switch to local Ollama (runtime fix, no code config)

The OpenRouter key in `infra/.env` was rejected (`401 User not found` - expired/rotated). Switched the stack to the local Ollama server:

- `infra/.env`: `LLM_PROVIDER=ollama`, `LLM_MODEL=qwen2.5:7b`, `LLM_API_KEY=ollama` (dummy - Ollama needs no key).
- `orchestrator/llm.py` (+62 lines): new `_ollama_completion()` - talks to `http://127.0.0.1:11434/api/chat` directly via httpx, bypassing litellm.

Why bypass litellm? Found by experiment:
1. `llama3.2:latest` (3B) ignores tool schemas entirely - writes Python scripts instead of calling the `bash` tool.
2. `qwen2.5vl:7b` calls tools, but after the first round emits empty `cmd` arguments forever.
3. Direct Ollama API test: the same conversation answers correctly the moment the tool result is present. => litellm's Ollama adapter was dropping tool-result messages, so the model never saw command output and re-issued tool calls.
4. `_ollama_completion` maps OpenAI-style messages to Ollama's native format: `tool` role messages, assistant `tool_calls` with dict args, and translates responses back to the OpenAI shape the agent loop expects (JSON-string arguments, generated call ids).

## Tests

7. `orchestrator/test_agent.py` - `test_on_step_fires_per_tool_step`: fake brain does 2 tool calls then answers; asserts the callback received both commands in order with exit codes.
8. `orchestrator/test_agent_api.py` - `test_agent_run_stream_emits_steps`: monkeypatched `run_agent` emits 2 steps via `on_step`, then returns a result; asserts the SSE body contains both `event: step` frames and the `event: result` frame with the answer.
9. `orchestrator/test_llm.py` - all 4 litellm tests now pin `LLM_PROVIDER`/`LLM_MODEL` env vars so they never depend on local `infra/.env` contents; new `test_ollama_native_path_translates_tool_calls` monkeypatches httpx and asserts the message translation both ways (dict args in, JSON-string args out).

## Verification

- `ruff check .`, `ruff format --check .`, `mypy` on all changed files: clean.
- `pytest -q`: 16 passed (13 previous + 3 new).
- Frontend: `bun x tsc --noEmit` clean; `bun run build` succeeds.
- Live stream through the bridge (`curl -N ... /api/agent/run/stream`):
  - task 1: 1 step (`python3 --version`, exit 0, 362ms) + result: "The version of Python installed in the sandbox is Python 3.12.13."
  - task 2: 1 step (`ls -1 /usr | wc -l`, exit 0, 314ms) + result: "There are 9 files in the `/usr` directory."
- Infrastructure note: Docker Desktop and the sandbox gateway (`./target/debug/sandbox-gateway`, :8080) had died overnight - restarted both; `make dev-gateway` and `open -a Docker` restore the stack.

## Files touched

- `orchestrator/agent.py` (+9 lines)
- `orchestrator/main.py` (+30 lines)
- `orchestrator/llm.py` (+62 lines, ollama native path)
- `orchestrator/test_agent.py` (+33 lines)
- `orchestrator/test_agent_api.py` (+27 lines)
- `orchestrator/test_llm.py` (+41 lines, env pinning + native path test)
- `frontend/src/index.ts` (+19 lines)
- `frontend/src/lib/client.ts` (+50 lines)
- `frontend/src/lib/use-chat.ts` (2 lines changed)
- `frontend/src/App.tsx` (4 lines changed)
- `infra/.env` (provider/model/key switched to Ollama - not committed, gitignored)

## Next

- Commit + push, watch CI, then try the two-step task from the earlier loop demo (expect multiple `step` frames now that tool results actually reach the model).