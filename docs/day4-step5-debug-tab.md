# Day 4 — Step 5: APITester → debug tab

## Topic

Decision step: keep the raw API tester or remove it. **Kept**, as a
**debug tab** — one click away from the chat, for raw API testing (including
driving the real robot) without touching code.

## What I did

1. **`frontend/src/App.tsx`** — added a small `chat | debug` toggle in the
   header (two buttons, no new deps — no Tabs package needed). Debug view
   renders the `APITester` inside a card.
2. **`frontend/src/APITester.tsx`** — upgraded so it can actually test the
   robot API:
   - `POST` added to the method select (was GET/PUT only);
   - optional **JSON body** field (e.g. `{"task": "what is 2+2"}`), sent as
     `application/json` when present.

## Why

- Raw API testing stays one click (spec's goal), and now it works for
  `/api/agent/run` — the endpoint that matters.
- Zero new dependencies: a two-button toggle replaces what would otherwise be
  a radix Tabs install + lockfile churn.

## What change it brings

- Header toggle: **chat** (the robot console) ↔ **debug** (method + endpoint +
  JSON body + raw response viewer).
- In debug mode you can POST a task straight to `/api/agent/run` and see the
  exact JSON the chat renders.

## Where (file → lines)

| File | Lines | Change |
|---|---|---|
| `frontend/src/App.tsx` | 12 | `view` state (`chat`/`debug`) |
| `frontend/src/App.tsx` | 30-54 | header toggle buttons + conditional debug card |
| `frontend/src/APITester.tsx` | 19-26 | POST method + JSON body in `fetch` |
| `frontend/src/APITester.tsx` | 46-47 | `POST` in method select |
| `frontend/src/APITester.tsx` | 59-66 | JSON body textarea |

## Verified

- `bun x tsc --noEmit` — clean; `bun run build` — passes.
- Live dev bundle on :3000 contains the new code ("JSON body" + error card
  strings present in the served bundle).
