# Day 4 — Step 2: API types + client (`frontend/src/lib/`)

## Topic

The UI needs typed access to the robot API. Step 2 adds the contract layer:
TypeScript types that mirror the orchestrator's JSON, and a small client with
error handling — the only place the UI talks to `/api/*`.

## What I did

1. **`frontend/src/lib/agent.ts`** — pure types:
   - `ToolResult` — the sandbox command result (`exit_code`, `stdout`,
     `stderr`, `timed_out`, `duration_ms`).
   - `ToolStep` — one diary entry (`type: "tool"`, `cmd`, `result`).
   - `AgentRunResponse` — the full API response: `{ok, answer?, error?,
     steps[]}` — mirrors `run_agent`'s return exactly.
   - `HealthResponse` — `{status, service?}` for the UI's offline badge.

2. **`frontend/src/lib/client.ts`** — the only fetch code in the app:
   - `runAgent(task)` — POSTs to `/api/agent/run` (same-origin, via the Step 1
     proxy). Two error paths, both returning a **normal `AgentRunResponse`**
     so the UI never has to try/catch:
     - network failure → `{ok:false, error:"network error: …", steps:[]}`
     - non-2xx (422 empty task, 502 orchestrator down) →
       `{ok:false, error:"server error <status>: <body>", steps:[]}`
   - `checkHealth()` — GET `/api/health`; any failure → `{status:"down"}`.

## Why

- **One contract, one place:** every future feature (chat, trace viewer,
  sessions) consumes `AgentRunResponse`; if the API changes, exactly two files
  change.
- **Errors as data, not exceptions:** the robot API already returns
  `{ok:false, error}` — the client preserves that shape for *all* failures, so
  the UI renders one error card, not five special cases.
- **Same-origin by design:** the client never knows the orchestrator's URL —
  it's behind the Bun proxy (Step 1).

## What change it brings

- `runAgent("list files")` → typed `{ok, answer, steps}` from anywhere in the
  UI; Step 3 (chat UI) can be written against stable types.
- A broken/absent orchestrator now produces a friendly `{ok:false, error}`
  instead of a raw `TypeError: fetch failed`.

## Where (file → lines)

| File | Lines | Change |
|---|---|---|
| `frontend/src/lib/agent.ts` | 1-20 | new file — API types (`ToolResult`, `ToolStep`, `AgentRunResponse`, `HealthResponse`) |
| `frontend/src/lib/client.ts` | 1-24 | new file — `runAgent()` (network + non-2xx handling), `checkHealth()` |

## Verified

- `bun run build` — passes.
- `bun x tsc --noEmit` — clean (0 errors).
- Runtime shape already proven in Step 1's live run (same JSON through the
  proxy); the UI wires it in Step 4.
