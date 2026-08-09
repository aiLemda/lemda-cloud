# Step 1 - Wire LLM (LiteLLM) into the orchestrator

Goal: prove the orchestrator can talk to a real LLM through LiteLLM using the free OpenRouter key, and make the call reproducible from both Python and the HTTP API.

## What changed, file by file

### `orchestrator/pyproject.toml`
- Added `litellm` dependency (installed v1.96.0, resolves OpenAI SDK, tiktoken, huggingface-hub, etc.)
- Effect: the orchestrator now has a universal LLM client that supports every major provider behind one API.

### `infra/.env` (gitignored - never committed)
- Added:
  ```
  LLM_PROVIDER=openrouter
  LLM_API_KEY=sk-or-v1-...          # real key
  LLM_MODEL=openrouter/free
  ```
- Effect: the real key lives only on disk, never in git. `.env` already ignored via `.gitignore`.

### `infra/.env.example` (committed template)
- Replaced the real key with `sk-or-v1-YOUR_OPENROUTER_KEY`
- Effect: the repo stays clean if committed; anyone cloning knows the exact variable names.

### `orchestrator/llm.py` (new)
- `LLMSettings` (pydantic-settings) loads `infra/.env` from the repo root (resolved from `__file__`, so it works regardless of where uvicorn is launched from).
- `ask_llm(prompt, timeout_s=120)` calls `litellm.completion(model="openrouter/<MODEL>", api_key=..., ...)` and returns the reply text.
- Effect: switching providers later (Gemini, Groq, Anthropic, OpenAI) = changing 3 lines in `.env`, zero code changes. This is the "abstraction" from Ch 47.

### `orchestrator/main.py`
- Added `GET /llm/ping` -> calls `ask_llm("Reply with exactly: ok")`, returns `{"model": ..., "reply": ...}`
- Effect: the live LLM loop is now exposed over HTTP for the UI and for manual testing.

## Proof it works (real output, 9 Aug 2026)

```
$ uv run python -c "from llm import ask_llm; print(ask_llm('Reply with exactly: ok'))"
ok

$ curl http://127.0.0.1:8123/llm/ping
{"model":"openrouter/openrouter/free","reply":"ok"}
```

Note: `openrouter/free` is OpenRouter's auto-router - it picks any currently-free model and never 404s when the free roster rotates. Free tier limits: ~20 req/min, ~50 req/day (no credits purchased).

## How to test it yourself

```
cd ~/Desktop/devin-clone/orchestrator
uv run uvicorn main:app --reload --port 8010
curl http://127.0.0.1:8010/llm/ping
```

## Next steps
- Fix `make dev-fleet` and orchestrator port 8000 -> 8010 (Clario owns 8000)
- Day 1 sandbox v0: Rust gateway `POST /exec` + Docker container with egress allowlist
- Benchmark `cohere/north-mini-code:free` vs `openai/gpt-oss-20b:free` and pin the winner in `.env`
