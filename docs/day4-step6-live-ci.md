# Day 4 — Step 6: Live test + CI

## Topic

Proof + ship: the whole Day 4 build (proxy → types → state → UI → debug tab)
verified live against the real stack, committed, pushed, and CI green.

## What I did

1. **Local build** — `bun run build` passes (CI parity).
2. **Live stack** — gateway :8080, orchestrator :8000, frontend :3000 all up.
3. **Task 1 (tool task)** — `list the files in the sandbox root and tell me
   the Python version` through the frontend proxy:

   ```
   ok: true | steps: 2
   step 1: run_bash('ls -la /')   exit=0
   step 2: run_bash('python --version')  exit=0
   answer: **Files in the sandbox root (`/`):** total 56 … (Python version included)
   ```

   In the browser: type it → 🧠 thinking… → answer bubble + robot diary with
   both steps, exit badges, durations, collapsible output.
4. **Task 2 (no tools)** — `what is 2+2`:

   ```
   ok: true | steps: 0 | answer: 4
   ```

   Instant answer, no sandbox touched — the "knows when to stop" proof, now
   visible in the UI.
5. **Commit + push + CI** — all Day 4 files committed; CI runs
   `bun run build` on the frontend job (plus ruff/mypy/pytest on the
   orchestrator — untouched this day).

## Why

- Step 6 exists so Day 4 ends the way Day 3 did: **proven live, pushed, and
  green** — the standing discipline of the project.

## What change it brings

- `http://localhost:3000` is a working robot console (chat + debug tabs,
  health dot, full trace viewer).
- `main` now contains the complete Days 1-4 chain: sandbox → loop → API →
  proxy → chat UI.

## Where (file → lines)

| File | Lines | Change |
|---|---|---|
| — | — | no code changes; live verification + commit |

## Verified

- `bun run build` — passes locally (same as CI's frontend job).
- Task 1: 2 real tool steps, exit 0, full answer. Task 2: 0 steps, `4`.
- Services left running for manual browser checks.
