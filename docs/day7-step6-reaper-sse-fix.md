# Day 7 - Step 6: Conversation reaper + SSE idle timeout fix

Two closing fixes for Day 7:

1. **Conversation TTL reaper** - idle conversations are evicted from the store, mirroring the gateway's sandbox-session reaper.
2. **SSE idle timeout** - the Bun dev server's 10s idle timeout killed live agent streams whenever a run sat quiet (Docker cold start, slow model). Bumped to 180s.

## 1. Conversation reaper

- `orchestrator/conversations.py` - `ConversationStore` now takes `ttl_secs` and `reap_interval_secs`; `reap_expired()` evicts conversations whose `updated_at` is older than the TTL (only writes count as activity - reads don't extend life, same as the gateway).
- `orchestrator/main.py` - store is configured from env (`CONVERSATION_TTL_SECS`, default 3600; `CONVERSATION_REAP_INTERVAL_SECS`, default 60) and a background `asyncio` reaper loop runs under the FastAPI lifespan (cancelled on shutdown).
- Tradeoff: a generous default TTL keeps the "reload-safe chat" story intact, but the mechanism is identical to the sessions reaper so the whole system behaves consistently.

## 2. SSE idle timeout

- `frontend/src/index.ts` - `serve({ idleTimeout: 180, ... })`. Long agent runs between tool steps no longer drop the stream.

## Tests

- `test_reaper_evicts_idle_but_keeps_fresh` - an aged conversation (timestamp forced to 0) is evicted; a freshly-written one survives. Deterministic, no sleeps.
- `test_reaper_leaves_everything_fresh_untouched` - reaping a store with only fresh conversations removes nothing.
- `pytest -q`: 36 passed; ruff + mypy clean; `tsc --noEmit` + `bun run build` clean.

## Live verification

- Orchestrator restarted with `CONVERSATION_TTL_SECS=3`, `CONVERSATION_REAP_INTERVAL_SECS=1`: two conversations created, none written recently -> both evicted by t=4s (a message written at t=0 was also past the 3s TTL, so the store emptied - correct behaviour).
- Full agent run through the bridge after a clean Bun restart: "what is 6 times 7?" -> answer 42 with 29 streamed `answer_token` deltas - the stream survived the whole run (the stale Bun process without the idleTimeout bump had been killing it).

## Files touched

- `orchestrator/conversations.py` (+17 lines)
- `orchestrator/main.py` (+15 lines)
- `orchestrator/test_conversations.py` (+22 lines)
- `frontend/src/index.ts` (+5 lines)

## Day 7 summary

Steps: conversation memory (step 2) -> token streaming / typewriter (step 3) -> reload-safe conversations (step 4) -> conversation picker (step 5) -> reaper + SSE fix (step 6). All shipped on `main`, CI green 3/3 throughout, 36 python tests + 21 rust tests + tsc/build.