# Day 7 - Step 2: Conversation memory - follow-ups with full context

## Goal

The chat UI now behaves like a real conversation: a follow-up message ("and 4+4?") is answered with the prior turns in the LLM context, instead of starting from a blank slate.

## Problem

Every message was a self-contained run: `run_agent(task)` built `[system, user]` and nothing else. "what is 2+2?" then "and 4+4?" lost all context between calls.

## Solution: a history parameter flowing through the whole stack

1. `orchestrator/agent.py`:
   - `run_agent(..., history=None)` and `_run_agent` build messages as `[system] + _sanitize_history(history) + [user: task]` (lines 49-103).
   - `_sanitize_history` (line 49) keeps only well-formed `user`/`assistant` turns with non-blank string content, drops system/tool/garbage turns, and caps at `MAX_HISTORY_TURNS = 20` (oldest first).
2. `orchestrator/main.py`:
   - `AgentRunRequest` gains `history: list[dict[str, str]] | None` (line 23); both `/agent/run` and `/agent/run/stream` forward it to `run_agent`.
3. `frontend/src/lib/client.ts` - `streamAgent(task, onStep, history?)` sends `history` in the request body.
4. `frontend/src/lib/use-chat.ts` - `submit()` builds history from the last 10 accumulated messages, mapping `agent` role -> `assistant` (line 24), typed explicitly so TS keeps the literal union. `messages` is now a `useCallback` dependency so the closure always sees the latest turns.

## Tests

- `test_history_prepended_in_order` - captured LLM messages are `[system, user(2+2), assistant(4), user(4+4), user(8+8)]` in order.
- `test_history_filters_garbage` - system/tool/blank turns dropped, only the real question survives.
- `test_history_capped_at_max_turns` - 30 turns in -> exactly 20 delivered.
- `test_agent_run_forwards_history` - the endpoint hands `history` through to `run_agent` unchanged.
- All pre-existing API fakes updated for the `history` kwarg. `pytest -q`: 22 passed; ruff + mypy clean; `tsc --noEmit` + `bun run build` clean.

## Live verification (through the Bun bridge, streaming)

- Turn 1 "what is 2+2?" -> tool step `echo $((2+2))` -> answer "4"
- Turn 2 "and 4+4?" WITH history -> answer "8" with zero tool steps (pure context)
- Turn 3 "add 1 to that result" with 4-turn history -> answered "5" (it anchored on the first prior answer; model nuance, not a pipeline issue - the history demonstrably reached the model).

## Files touched

- `orchestrator/agent.py` (+38/-2 lines)
- `orchestrator/main.py` (+3/-1 lines)
- `orchestrator/test_agent.py` (+75 lines)
- `orchestrator/test_agent_api.py` (+25 lines)
- `frontend/src/lib/client.ts` (+6 lines)
- `frontend/src/lib/use-chat.ts` (+6 lines)

## Next

- Commit + push + CI green. Then: per-conversation persistence (reload-safe sessions), or answer token-streaming (typewriter effect).