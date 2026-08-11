# Day 4 — Step 4: Chat UI (`frontend/src/App.tsx` + components)

## Topic

The face of the robot: a chat UI where you type a task, watch the robot
think, and read both its answer and its full work diary (the trace). Rides on
the Step 1 proxy, Step 2 types/client, Step 3 chat state.

## What I did

1. **`frontend/src/components/trace-viewer.tsx`** (new, 81 lines) — the star.
   Renders `steps[]` as a vertical **robot diary**:
   - each step = `🧠 think` + `run_bash("cmd")` + `exit` badge (green/red) +
     duration, then `👀 look` + output;
   - stdout/stderr in a **collapsible** `<details>` (no new deps — native
     HTML), stderr tinted red, `⏰ timed out` warning when applicable;
   - header: "🤖 robot diary — N steps".
2. **`frontend/src/App.tsx`** (rewritten, 158 lines):
   - **Message list** — scrollable (`overflow-y-auto`, auto-scrolls to the
     bottom on new messages via a ref + effect); user bubbles right
     (primary), robot left (muted).
   - **Input + Send** — Enter submits (form), disabled while running or when
     empty.
   - **🧠 thinking…** bubble with `animate-pulse` while `running`.
   - **On completion** — answer bubble + `TraceViewer` underneath.
   - **Error state** — red "the robot tripped" card with the raw error
     (`ok:false` or fetch failure).
   - **Empty state** — friendly centered "What should the robot do?" with a
     suggestion prompt.
   - **Health badge** — "robot online/offline" dot from `checkHealth()`.
   - Template logos/APITester removed from the app (APITester file kept as a
     debug tool).

## Why

- **See the robot think (the point of the project):** the trace is rendered
  as a readable story — what it ran, what it saw, exit codes, timing — not a
  JSON blob.
- **Zero new dependencies:** `<details>`, tailwind classes and the existing
  shadcn primitives cover everything.
- **Every state handled:** idle/running/done/error all have a home, so the UI
  never shows a blank screen mid-run or on failure.

## What change it brings

- A browser on `http://localhost:3000` is now a full robot console: ask a
  task → watch it think → read the answer + diary.
- The `steps[]` observability seed from Day 3 finally has eyeballs on it.

## Where (file → lines)

| File | Lines | Change |
|---|---|---|
| `frontend/src/components/trace-viewer.tsx` | 1-81 | new — `StepCard` (think/look, exit badge, collapsible output) + `TraceViewer` |
| `frontend/src/App.tsx` | 1-158 | rewrite — chat shell, messages, states, input, health badge |

## Verified

- `bun x tsc --noEmit` — clean; `bun run build` — passes.
- Served bundle on :3000 contains the new app (grep: robot diary/error/empty
  strings present).
- Live end-to-end through the proxy: robot ran `ls -la /` → `python3
  --version` → combined re-check (3 steps, all exit 0) → full answer. This is
  exactly the JSON the TraceViewer renders.
- Services left running: gateway :8080, orchestrator :8000, frontend :3000 —
  open `http://localhost:3000` to try it.
