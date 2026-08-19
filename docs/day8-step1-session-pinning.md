# Day 8 - Step 1: Per-conversation sandbox pinning

## Goal

A conversation's workspace persists across turns. Today every agent run spun up a fresh container and threw it away - "create a file" then "read it back" failed. Now a conversation pins one sandbox: write the file in turn 1, read it in turn 3.

## How it works

1. `orchestrator/sandbox.py` - `session_alive(sid)` asks the gateway's `GET /sessions` whether a session is still tracked (the gateway's own reaper may have evicted a pinned session while the conversation sat idle).
2. `orchestrator/agent.py` - `run_agent(..., session_id=None)` - a pinned session is reused and never closed by the run; an unpinned run keeps the old create/close-in-`finally` behaviour.
3. `orchestrator/conversations.py` - each conversation gains a `session_id` slot (`get_session`/`set_session`); `reap_expired()` now returns `(cid, session_id)` pairs so the caller can close the sandboxes it evicts.
4. `orchestrator/main.py`:
   - `AgentRunRequest.conversation_id`; both `/agent/run` and `/agent/run/stream` route through `_resolve_session`:
     - no conversation -> unpinned run (agent owns lifecycle);
     - unknown conversation -> unpinned run (graceful);
     - pinned + alive -> reuse;
     - pinned but stale (gateway reaped it) -> create fresh and re-pin.
   - the lifespan reaper loop closes the pinned session of every evicted conversation.
5. `frontend/src/lib/use-chat.ts` + `client.ts` - `streamAgent` sends `conversation_id` so the UI's turns pin to the current chat.

## Tests

- `test_run_agent_reuses_pinned_session` - with `session_id` given, no session is created or closed and exec runs in the pinned one.
- `test_pinned_session_reused_when_alive` - alive pinned session is passed through; nothing created.
- `test_stale_pinned_session_recreated` - dead pinned session is replaced with a fresh one and re-pinned.
- `test_unknown_conversation_runs_unpinned` - unknown conv -> `session_id=None`, no container created.
- `test_session_pin_and_reaper_releases_it` - reaper returns the pinned session with the evicted conversation.
- `pytest -q`: 41 passed; ruff + mypy clean; `tsc --noEmit` + `bun run build` clean.

## Live verification (through the Bun bridge)

- Conversation A: turn 1 `printf 'HELLO-WORKS' > /tmp/memo.txt` -> "written"; turn 2 `cat /tmp/memo.txt` -> "The content of /tmp/memo.txt is: HELLO-WORKS" (the file survived a separate agent run).
- Conversation B: `cat /tmp/memo.txt` -> "does not exist" - each conversation's sandbox is its own.
- Fleet showed exactly 2 live sessions (one per conversation) instead of one-per-run.

## Bug caught live

The first attempt looked broken: `session_alive` compared against `s.get("id")` but the gateway's list uses `session_id`, so every run created a fresh container and the file vanished. Fixed by matching the real key.

## Files touched

- `orchestrator/sandbox.py` (+12 lines)
- `orchestrator/agent.py` (+9/-8 lines)
- `orchestrator/conversations.py` (+26/-4 lines)
- `orchestrator/main.py` (+32/-6 lines)
- `orchestrator/test_agent.py` (+26 lines)
- `orchestrator/test_agent_api.py` (+78 lines)
- `orchestrator/test_conversations.py` (+13 lines)
- `frontend/src/lib/client.ts` (+5/-2 lines)
- `frontend/src/lib/use-chat.ts` (+1 line)

## Next

Conversation-scoped installs (pip/npm cache in the pinned sandbox), or wiring the picker's resumed chats straight back into their pinned workspace.