# Day 7 - Step 5: Conversation picker - resume any past chat

## Goal

Every saved conversation is reachable from the header: a "chats" dropdown lists past chats (first user message + message count + age), and picking one loads it back into the chat window. Combined with step 4's store, this closes the persistence loop - chats are not just stored, they are resumable.

## Solution

1. `orchestrator/conversations.py` - `list()` now includes `preview`: the first user message of each conversation (or "" for an empty chat).
2. `frontend/src/lib/agent.ts` - `ConversationSummary` gains `preview`.
3. `frontend/src/lib/use-chat.ts`:
   - `conversations` state + `refreshConversations()` (refetched on mount, on new-chat, on conversation switch, and when a fresh conversation is created).
   - `selectConversation(id)` - guards against mid-run switches, loads the conversation, swaps the message list, persists the id to localStorage, clears the answer/steps/error.
4. `frontend/src/App.tsx` - a 💬 chats dropdown in the header (disabled while running): renders each conversation's preview, `N msgs · relative age` (a small `timeAgo` helper), highlights the active one, and closes via a fixed backdrop. The "+ new chat" button keeps working.

## Tests

- `test_list_shows_first_user_message_as_preview` - the list entry for a two-message conversation exposes `preview` = the user message and `message_count` = 2. `test_list_conversations_newest_first` also asserts `preview` is present. `pytest -q`: 34 passed; ruff + mypy clean; `tsc --noEmit` + `bun run build` clean.

## Live verification (through the Bun bridge)

- Created three conversations ("what is 2+2?", "what is the meaning of life?", "list files in the sandbox") - the list returns all three, newest first, with correct previews and message counts.
- Resumed the oldest (conv_9eed...) - both turns restored: `[('user', 'what is 2+2?'), ('assistant', '4')]`.
- Continued it with a follow-up using the restored history: "and 4+4?" -> `answer: "8"`, zero tool steps (pure context), streamed via `answer_token` events - through the bridge.

## Note

The Bun dev server's SSE `idleTimeout` (10s) can kill a stream that sits idle during an agent run if Docker is mid-restart; with the gateway healthy the stream completes normally. Worth raising for long tool loops in a future step.

## Files touched

- `orchestrator/conversations.py` (+7 lines)
- `orchestrator/test_conversations.py` (+17 lines)
- `frontend/src/lib/agent.ts` (+1 line)
- `frontend/src/lib/use-chat.ts` (+48/-10 lines)
- `frontend/src/App.tsx` (+44/-6 lines)

## Next

A conversation TTL reaper for the orchestrator store (mirroring the gateway's), or answer token-streaming backpressure.