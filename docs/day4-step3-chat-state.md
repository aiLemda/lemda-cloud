# Day 4 — Step 3: Chat state (`frontend/src/lib/use-chat.ts`)

## Topic

The UI's brain — a React hook that owns the chat session: what's been said
(messages), what phase the robot is in (state), and the last run's outcome
(answer + steps + error).

## What I did

`useChat()` (`frontend/src/lib/use-chat.ts`, 57 lines):

- **State machine** — `ChatState = "idle" | "running" | "done" | "error"`:
  ```
  idle ──submit(task)──► running ──ok──► done
                             │
                             └──!ok──► error
  ```
- **`messages`** — `{role: "user" | "agent", content}[]`; user's task is
  appended on submit, the robot's `answer`/`error` appended when it returns.
- **While running** — `state === "running"` (UI renders the 🧠 thinking…
  indicator; the hook also refuses to double-submit while running).
- **On completion** — `answer` + `steps` (the full trace) on success; `error`
  on failure; both paths also land a message in the list.
- **`reset()`** — clears everything back to `idle` (future "New chat" button).

## Why

- **One source of truth:** all chat state in one hook — Step 4's UI just
  renders it; no scattered `useState`s across components.
- **Guards:** blank tasks and double-clicks while running are rejected in the
  hook (single place, testable, UI-proof).
- **Prepared for the trace:** the hook keeps `steps` separate from `answer`,
  so Step 4 can render the robot's diary under the answer.

## What change it brings

- The UI can now be written declaratively: "if state is X, show Y".
- A robot run's full lifecycle (think → answer/trace → error) has one owner.

## Where (file → lines)

| File | Lines | Change |
|---|---|---|
| `frontend/src/lib/use-chat.ts` | 1-57 | new file — `ChatMessage`, `ChatState`, `useChat()` hook (`submit`, `reset`, states, messages) |

## Verified

- `bun x tsc --noEmit` — clean (0 errors).
- `bun run build` — passes.
- Runtime behavior rides on Step 1/2's proven client; Step 4 exercises it live
  in the browser.
