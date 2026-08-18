# Day 7 - Step 4: Reload-safe conversations

## Goal

Refresh the page mid-conversation and the chat comes back. Chat history now lives server-side; the UI keeps a conversation id and restores it on load.

## Solution

1. `orchestrator/conversations.py` - a small in-memory store (mirrors the gateway's sandbox session model): `create()`, `list()` (newest first), `get()`, `append()` (capped at `MAX_MESSAGES = 50`). Thread-safe via a lock.
2. `orchestrator/main.py` - four endpoints:
   - `POST /conversations` (201) -> `{id, messages: []}`
   - `GET /conversations` -> summaries `{id, message_count, updated_at}`
   - `GET /conversations/{cid}` -> `{id, messages}` (404 if unknown)
   - `POST /conversations/{cid}/messages` with `{role: user|assistant, content}` (role validated by pydantic `Literal`; 404 if unknown)
3. Bridge (`frontend/src/index.ts`) - generic `forwardJson` helper + routes `/api/conversations`, `/api/conversations/:id`, `/api/conversations/:id/messages`.
4. `frontend/src/lib/client.ts` - `createConversation`, `getConversation`, `appendConversationMessage`, `listConversations` (+ `ChatTurn`/`Conversation`/`ConversationSummary` types in `agent.ts`).
5. `frontend/src/lib/use-chat.ts`:
   - On mount: if `localStorage["devin_clone_conversation_id"]` exists, `GET` it and restore the message list; a 404 clears the stale id.
   - On submit: lazily `POST /conversations` (id persisted to localStorage), append the user message, run the agent, then append the assistant message (answer or error text). Conversation failures degrade gracefully - chat still works locally.
   - `reset()` now also drops the stored id, so "+ new chat" starts fresh while old conversations stay on the server.
6. `App.tsx` - "+ new chat" header button.

## Tests

- `test_conversations.py` (5): create+get, append order, bad role -> 422, missing conversation -> 404 on both read and append, list newest-first with `message_count`. `pytest -q`: 33 passed; ruff + mypy clean; `tsc --noEmit` + `bun run build` clean.

## Live verification (through the Bun bridge)

- Full CRUD: create -> append user -> append assistant -> GET restores both turns -> list -> 404 on unknown id.
- Simulated user flow: "what is 3+3?" streamed (tool step + answer tokens) -> answer "6" appended; reload-GET returns `[(user, "what is 3+3?"), (assistant, "6")]`; follow-up "and 10+10?" with restored history -> "20".

## Files touched

- `orchestrator/conversations.py` (new, 65 lines)
- `orchestrator/main.py` (+38 lines)
- `orchestrator/test_conversations.py` (new, 47 lines)
- `frontend/src/index.ts` (+35/-1 lines)
- `frontend/src/lib/agent.ts` (+17 lines)
- `frontend/src/lib/client.ts` (+50 lines)
- `frontend/src/lib/use-chat.ts` (+32/-6 lines)
- `frontend/src/App.tsx` (+9 lines)

## Next

Conversation resume across devices (list picker in the UI), or a conversation TTL reaper for the server store.
