# Day 4 — Chat UI: line-level report

Standing-rule report: what, why, what changed, and exactly where (file:lines).

## What

Gave the robot a face. Days 1-3 built the brain (`run_agent`), the phone
(`llm`), the door (`/agent/run`) and the sandbox. Day 4 built the browser
console: a chat where you type a task, watch the robot think, and read both
its answer and its full work diary (`steps[]` trace), plus a debug tab for raw
API testing. The bridge is a server-side proxy on the Bun server, so the
backend stays CORS-closed.

## Why

- **The trace is the product:** Day 3 planted observability in `steps[]`;
  Day 4 puts eyeballs on it — the "robot diary" viewer renders each tool call,
  exit code and output as a readable story.
- **Same-origin, closed backend:** the browser only ever talks to `:3000`;
  the Bun server forwards to the orchestrator. No CORS middleware was added to
  FastAPI.
- **Errors as data:** every failure (network, non-2xx, `ok:false`) arrives as
  a normal `{ok, error, steps}` — one error card handles all cases.

## What changed (file → lines)

### `frontend/src/index.ts` (edited, 71 lines) — the bridge
| Lines | Content |
|---|---|
| 4 | `ORCHESTRATOR_URL` from `BUN_ORCHESTRATOR_URL` (default `http://127.0.0.1:8000`) |
| 11-18 | `GET /api/health` proxy → `{status:"down"}` + 502 if unreachable |
| 20-36 | `POST /api/agent/run` proxy → pass-through JSON + status; 502 wrapper |

### `frontend/src/lib/` (new) — the contract
| File | Lines | Content |
|---|---|---|
| `agent.ts` | 1-25 | `ToolResult`, `ToolStep`, `AgentRunResponse {ok, answer?, error?, steps[]}`, `HealthResponse` |
| `client.ts` | 1-27 | `runAgent(task)` — network + non-2xx → normal `{ok:false,…}`; `checkHealth()` |
| `use-chat.ts` | 1-52 | `useChat()` hook — `idle→running→done\|error`, `messages[]`, `submit` (guards blank/double), `reset` |

### `frontend/src/components/trace-viewer.tsx` (new, 73 lines) — the star
| Lines | Content |
|---|---|
| 5-9 | `formatMs` duration helper |
| 11-58 | `StepCard`: 🧠 think + `run_bash("cmd")` + exit badge (green/red) + duration; 👀 look + collapsible `<details>` output (stderr red, timeout warning) |
| 62-73 | `TraceViewer`: "🤖 robot diary — N steps" + step list |

### `frontend/src/App.tsx` (rewritten, 157 lines) — the console
| Lines | Content |
|---|---|
| 12-16 | state: `task`, `online` (health), `view` (`chat`/`debug`) |
| 18-29 | effects: health check on mount; auto-scroll on new messages |
| 31-36 | `onSubmit`: Enter-to-send, rejects blank/while-running |
| 39-68 | header: title, chat/debug toggle, online dot |
| 70-75 | debug view renders `APITester` |
| 78-95 | empty state ("What should the robot do?") |
| 97-114 | message bubbles (user right/primary, agent left/muted) |
| 116-120 | 🧠 thinking… bubble (`animate-pulse`) |
| 122-132 | done: answer bubble + `TraceViewer` under it |
| 134-141 | error: red "the robot tripped" card |
| 143-155 | input + Send (disabled while running) |

### `frontend/src/APITester.tsx` (edited, 79 lines)
| Lines | Content |
|---|---|
| 19-26 | fetch with `POST` method + optional JSON body |
| 46-47 | `POST` added to method select |
| 59-66 | JSON body textarea (`{"task": "…"}`) |

### Docs (new)
| File | Topic |
|---|---|
| `docs/day4-step1-proxy-bridge.md` … `day4-step6-live-ci.md` | per-step reports |
| `docs/day4-chat-ui.md` | this report |

## Verified

- `bun x tsc --noEmit` — clean; `bun run build` — passes (CI parity).
- Live (through the proxy, = browser path):
  - `list the files… and tell me the Python version` → 2 real tool steps
    (`ls -la /`, `python --version`, both exit 0) + full answer.
  - `what is 2+2` → 0 steps, answer `4`.
- CI after push: orchestrator ✓ frontend ✓ sandbox-gateway ✓ (all green).

## How it works in one sentence

Browser on `:3000` → Bun proxy `/api/*` → orchestrator `/agent/run` →
`run_agent` loop → sandbox — and the whole diary comes back to the chat UI,
rendered as a collapsible robot diary under the answer.
