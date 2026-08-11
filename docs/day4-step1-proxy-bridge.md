# Day 4 — Step 1: Bridge the ports (the CORS problem)

## Topic

The browser (frontend on :3000) needs to call the orchestrator (FastAPI on
:8000), but cross-origin requests from a browser to a plain FastAPI server are
blocked by CORS — and the orchestrator has no CORS middleware (and we don't
want to open it). Day 4 Step 1 solves this with a **server-side proxy** on the
Bun server: the browser talks to its own origin (`/api/*`), and the Bun server
forwards to the orchestrator.

## What I did

Added two proxy routes to the Bun server (`frontend/src/index.ts`):

1. **`GET /api/health`** (`index.ts:9-18`) — forwards to
   `{ORCHESTRATOR_URL}/health`; returns `{"status":"down"}` + 502 if the
   orchestrator is unreachable (lets the UI show "robot offline" later).
2. **`POST /api/agent/run`** (`index.ts:20-36`) — forwards the request body
   to `{ORCHESTRATOR_URL}/agent/run`, passes through status and JSON, and
   returns a clean `{ok:false, error, steps:[]}` + 502 if unreachable.

Target URL comes from `BUN_ORCHESTRATOR_URL` (server-side env), defaulting to
`http://127.0.0.1:8000` (`index.ts:4`) — the Makefile's `dev-orchestrator`
port.

## Why

- **No CORS on the backend:** the browser stays same-origin (`:3000` → `:3000`),
  so FastAPI stays closed to foreign origins — the proxy keeps the backend pure.
- **Central error shape:** unreachable-orchestrator failures become a normal
  JSON response the UI can render, not a browser-network error.
- **Configurable:** point `BUN_ORCHESTRATOR_URL` elsewhere (prod host, port)
  without touching code.

## What change it brings

- `curl -X POST localhost:3000/api/agent/run -d '{"task": "..."}'` now drives
  the real robot — same as calling :8000 directly, but browser-safe.
- The UI (Step 4) will call only `/api/*` on its own origin.

## Where (file → lines)

| File | Lines | Change |
|---|---|---|
| `frontend/src/index.ts` | 4 | `ORCHESTRATOR_URL` from `BUN_ORCHESTRATOR_URL` (default :8000) |
| `frontend/src/index.ts` | 9-18 | `/api/health` proxy |
| `frontend/src/index.ts` | 20-36 | `/api/agent/run` proxy + 502 wrapper |

## Verified (live)

- `bun run build` — passes.
- Proxy health: `{"status":"ok","service":"orchestrator"}`.
- Proxy agent run, real stack: robot tried `echo "2+2" | bc` (bc missing,
  exit 127) → retried `python3 -c 'print(2+2)'` (exit 0, `4`) → double-checked
  `echo $((2+2))` (exit 0, `4`) → answer `4`. Full trace in `steps[]`.
- Unreachable test: with orchestrator down the proxy returns 502 + JSON error.

## Environment notes (fixed en route)

- `bun-plugin-tailwind@0.1.2` local install was corrupt (empty `index.mjs`);
  `bun install --frozen-lockfile` re-fetched a valid 1.58 MB file.
- `orchestrator/agent.py` had a stray syntax error (`if not cmd:f` at line 72)
  — reverted to the committed version.
- Docker Desktop had stopped; restarted for the sandbox demo.
