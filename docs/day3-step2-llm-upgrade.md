# Day 3 — Step 2: Upgrade the phone (`orchestrator/llm.py`)

## Topic

`orchestrator/llm.py` is the "phone" of the agent: the only module allowed to
talk to an LLM provider (OpenRouter today, via LiteLLM). This step upgraded it
from a single sync call into a resilient, async-capable layer.

Half of this step already landed during Day 3 Step 1 (the `chat(messages,
tools=None)` function that returns the full message with `tool_calls`, used by
the agent loop). This step finished the job.

## What I did

1. **Added fallback provider settings** to `LLMSettings`
   (`llm.py:21-23`): `LLM_FALLBACK_PROVIDER`, `LLM_FALLBACK_API_KEY`,
   `LLM_FALLBACK_MODEL`. These were already documented in
   `infra/.env.example` but were never implemented.
2. **Extracted `_completion()`** (`llm.py:26-43`): the actual LiteLLM call,
   parameterized by provider/key/model, so both `chat` and the fallback path
   share one code path.
3. **Automatic fallback in `chat()`** (`llm.py:59-88`): if the primary call
   throws (provider down, rate limit, bad key), it retries once with the
   fallback provider — but only if `LLM_FALLBACK_API_KEY` is configured.
   Otherwise it re-raises the original error.
4. **Added `achat()`** (`llm.py:91-96`): async twin of `chat` that runs the
   blocking LiteLLM call in a worker thread via `asyncio.to_thread`, so the
   server event loop is never blocked.
5. **Agent loop now uses the async phone** (`agent.py:57`):
   `await llm.achat(messages, tools=[BASH_TOOL])`.
6. **New tests** (`test_llm.py`, 4 offline tests): primary path passes tools +
   key through; fallback fires when primary fails and dials the backup; no
   fallback configured means the error propagates; `achat` returns the same
   result off the event loop.

## Why

- **Resilience:** `run_agent`/`/agent/run` depend on one provider. If OpenRouter
  is down or rate-limited, the whole agent dies. The fallback (e.g. Gemini via
  a second key) keeps the loop alive for a fraction of the code cost — it was
  already promised by `.env.example`, now it actually works.
- **Event-loop hygiene:** FastAPI's endpoints are async; `run_agent` awaited
  a sync LiteLLM call, which would freeze the entire server for up to 120s on
  one slow request. `achat` moves that off-thread.
- **Tests stay offline:** the fallback logic is pure routing around a
  monkeypatched `litellm.completion` — no network, no keys needed.

## What change it brings

- If you put `LLM_FALLBACK_PROVIDER=gemini`, `LLM_FALLBACK_API_KEY=...`,
  `LLM_FALLBACK_MODEL=gemini-2.5-flash` in `infra/.env`, agent requests
  automatically use Gemini when OpenRouter fails.
- The agent loop no longer blocks the FastAPI event loop.
- Behavior with a single key is unchanged (verified with a real call: reply
  `ok`, no tool_calls).

## Where (file → lines)

| File | Lines | Change |
|---|---|---|
| `orchestrator/llm.py` | 1-9 | imports + env path (asyncio added) |
| `orchestrator/llm.py` | 12-23 | `LLMSettings` fallback fields |
| `orchestrator/llm.py` | 26-43 | new `_completion()` (extracted) |
| `orchestrator/llm.py` | 46-56 | `ask_llm` unchanged |
| `orchestrator/llm.py` | 59-88 | `chat` with fallback logic |
| `orchestrator/llm.py` | 91-96 | new `achat()` |
| `orchestrator/agent.py` | 57 | loop uses `await llm.achat(...)` |
| `orchestrator/test_llm.py` | 1-81 | new file, 4 offline tests |

Verified: `ruff check` clean, `mypy` clean, `pytest` 11 passed
(3 sandbox + 4 agent + 4 llm), plus 1 live call to the real API.
