# Day 7 - Step 3: Typewriter answers - real token streaming

## Goal

The robot's final answer appears in the chat as the model generates it - word by word - instead of arriving as one block after the last tool step.

## How it works

The answer is streamed, not faked (no client-side typing animation over a finished string).

1. `orchestrator/llm.py`:
   - `_ollama_achat_stream` - talks to Ollama's native `/api/chat?stream=true` via `httpx.AsyncClient.stream` (NDJSON lines). Every content delta is pushed to `on_token` as it arrives; `tool_calls` are collected from the final chunk and translated to the same shape as the non-streaming path. Shared `_to_ollama_messages` now serves both paths.
   - `achat_stream` - provider-aware: Ollama streams natively; any other provider falls back to the full response delivered as a single token (the key check stays inside `chat`, so CI tests that fake `chat` keep working).
2. `orchestrator/agent.py`:
   - `run_agent(..., on_answer_token=...)` - the loop's LLM calls now go through `achat_stream` with an `on_token` callback.
   - `_AnswerTagFilter` - streams the content through, stripping `<answer>`/`</answer>` delimiters *in-flight*, even when a tag is split across token boundaries. A trailing run that could still become a tag is held back until the next token decides; anything longer than a tag can possibly be (15 chars) is flushed, so prose like "x < y" is never lost.
3. `orchestrator/main.py` - the stream endpoint wires `on_answer_token` to the SSE queue as `answer_token` events.
4. Frontend - `streamAgent(task, onStep, history, onAnswerToken?)` parses the new event; the hook appends each delta to the live `answer` state; `App.tsx` renders a typing bubble (`▍` cursor) as soon as tokens start arriving, swapping to the canonical result bubble when done.

The UI scrolls on `state` changes too, so the growing answer stays in view.

## Tests

- `test_achat_stream_ollama_deltas_and_tool_calls` - fake streaming client: content accumulates ("hel"+"lo"), tool_calls translated from the final chunk, `on_token` gets each delta.
- `test_achat_stream_falls_back_to_single_token` - non-Ollama provider delivers the whole answer as one token.
- `test_answer_tag_filter_strips_split_tags` - `<answ`+`er>hel`+`lo</`+`answer>` becomes "hello".
- `test_answer_tag_filter_flushes_held_non_tags` - "x < y" style prose is held briefly, then flushed - never lost.
- `test_run_agent_streams_answer_tokens` - tokens flow through `run_agent` with tags removed.
- `test_agent_run_stream_emits_answer_tokens` - endpoint emits two `answer_token` SSE events.
- All agent tests now fake at the `agent.llm.achat_stream` seam (the agent's real contract) instead of `llm.chat`, so they stay deterministic regardless of `infra/.env`. `pytest -q`: 28 passed; ruff + mypy clean; `tsc --noEmit` + `bun run build` clean.

## Live verification (through the Bun bridge)

- "tell me a 12-word sentence about sandboxes. do not use any tools" -> 13 `answer_token` events: "A sandbox provides a secure environment for testing code without affecting systems." - `<answer>` tags never leaked into the stream.
- "what is 7 times 6?" -> 1 `step` event (`echo $((7*6))` -> 42) then 35 `answer_token` deltas typing out the explanation, final result `"answer": "42"`.

## Files touched

- `orchestrator/llm.py` (+85/-4 lines)
- `orchestrator/agent.py` (+52/-12 lines)
- `orchestrator/main.py` (+5/-1 lines)
- `orchestrator/test_llm.py` (+90 lines)
- `orchestrator/test_agent.py` (+50/-12 lines)
- `orchestrator/test_agent_api.py` (+20 lines)
- `frontend/src/lib/client.ts` (+7 lines)
- `frontend/src/lib/use-chat.ts` (+2 lines)
- `frontend/src/App.tsx` (+12/-4 lines)

## Next

Per-conversation persistence (reload-safe sessions), or answer token-streaming polish (backpressure on very long answers).
