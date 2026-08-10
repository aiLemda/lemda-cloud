# Day 3 — Step 5: LIVE demo (the moment)

## Topic

The first end-to-end, live proof that the whole stack works with a real model
in the loop: orchestrator HTTP API → agent loop → real LLM (free OpenRouter)
→ real tool calls → real Docker sandbox → final answer. No fakes anywhere.

## What I did

Started both services (sandbox-gateway on :8080, orchestrator on :8010), then
POSTed two tasks to `/agent/run`.

**Demo 1 — tool-using task** (`list the files in the sandbox root and tell me
the Python version`):

```
ok: True
STEP 1 -> tool: ls -la          (exit 0, 1594ms)
STEP 2 -> tool: python3 --version  (exit 0, 765ms)
ANSWER: <file/dir listing> — Python version: 3.12.13
```

The robot's trace, exactly as designed: **THINK → `ls -la /` → LOOK → `python3
--version` → LOOK → answer**. Each step is in `steps[]` with raw stdout —
observability is built in.

**Demo 2 — no-tool task** (`what is 2+2`):

```
ok: True
tool steps used: 0
ANSWER: 4
```

Zero tool calls — the loop knows when to stop and answer directly.

## Why

- This is the whole point of Days 1-3: the loop actually works against a real,
  free model in a real sandbox. The earlier live `ls` demo (Step 3) proved one
  tool step; this proves the full multi-step chain and the stop-condition.
- Demo 2 proves the loop doesn't pattern-match "always call a tool" — it
  respects the model's decision to answer immediately (costs 1 call, saves the
  sandbox).
- All captured in `steps[]` — the trace IS the product (Day 45 observability).

## What change it brings

- Nothing in code — this step is **proof**, not a diff. (The only env change
  was starting the prebuilt gateway binary, which had been built but not run.)
- From now on, any change to the loop or the phone can be sanity-checked with
  the same two curl commands.

## Where (file → lines)

| File | Lines | Change |
|---|---|---|
| — | — | no code changes; live run only |

Cost: 4 LLM calls total on free tier. Verified live:

- Demo 1: 2 real tool steps, exit 0 both, correct answer (Python 3.12.13).
- Demo 2: 0 tool steps, correct answer (4).

Reproduce:
```bash
cd sandbox-gateway && ./target/debug/sandbox-gateway &        # :8080
cd orchestrator && uv run uvicorn main:app --port 8010 &      # :8010
curl -s -X POST localhost:8010/agent/run -H 'Content-Type: application/json' \
  -d '{"task": "what is 2+2"}'
```
