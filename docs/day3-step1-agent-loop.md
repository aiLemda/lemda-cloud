# Day 3, Step 1 - The agent loop engine (`orchestrator/agent.py`)

The brain learns to press its own button. This file turns the orchestrator from a
remote-controlled robot into one that thinks: decide a command -> run it in the sandbox ->
read the output -> repeat -> answer.

## The topic (ELI5)

An **agent loop** is: THINK -> ACT -> LOOK -> THINK -> ... -> DONE.

- THINK: the LLM decides the next shell command (or says "I'm done")
- ACT: we run that command in the sandbox (the `/exec` button from Step 2)
- LOOK: we show the output back to the LLM
- Repeat until the LLM answers, or we hit the safety limit (10 steps)

The LLM can press the button two ways:
1. **Tool calling (primary):** the LLM returns a structured
   `{"name": "run_bash", "arguments": {"cmd": "ls -la /"}}` message (the industry-standard
   way - what Devin / Claude Code do).
2. **Tag language (fallback):** some free models can't do tool calling, so we also teach:
   `<bash>command</bash>` = press the button, `<answer>text</answer>` = I'm done.
   Either way, the loop works. This resilience is the interview-gold part.

## What I did, file by file (with line ranges)

### NEW `orchestrator/agent.py` (111 lines) - the loop engine
- Lines 1-6: imports. Note lines 5-6: `import llm` and `import sandbox` (module imports,
  NOT `from x import y`). Why: tests monkeypatch `llm.chat` and `sandbox.sandbox_exec`;
  module-style imports let the patch take effect at call time. (Learned the hard way -
  function imports silently ignored the patch and hit the real network.)
- Line 8: `MAX_STEPS = 10` - the "unplug the robot" limit.
- Lines 10-18: `SYSTEM_PROMPT` - the rules of the game: one tool, network limited to
  GitHub/PyPI/npm, prefer short commands, `<answer>` protocol, `<bash>` fallback.
- Lines 20-33: `BASH_TOOL` - the JSON "button spec" in OpenAI tool-calling format
  (`type: function`, name `run_bash`, one required arg `cmd`).
- Lines 36-45: `_summarize()` - turns an ExecResult into a short readable string for the LLM
  (handles timeouts, stderr-only, normal stdout, no output).
- Lines 48-53: `run_agent(task, max_steps=10)` - builds the message history
  `[system, user task]` and an empty `steps` trace log.
- Lines 55-59: the loop head - one LLM call per iteration via `llm.chat(messages, tools=...)`.
  `# noqa: BLE001` is intentional: LLM providers throw a zoo of exception types (verified
  live - no common base class exists), and the loop must survive any of them.
- Lines 62-89: **tool-calling path** - if the model returned `tool_calls`, parse the JSON
  args (bad JSON -> empty cmd -> a helpful error result), run it with `sandbox.sandbox_exec`,
  record the step, append the result as a `role: "tool"` message, continue the loop.
- Lines 91-99: **tag fallback path** - no tool_calls but `<bash>cmd</bash>` present: run the
  last one, append the output as a plain `user` message, continue.
- Lines 101-105: **done path** - extract `<answer>...</answer>`, or treat any remaining text
  as the final answer; return `{"ok": True, "answer": ..., "steps": [...]}`.
- Lines 107-111: **safety exit** - 10 steps without an answer -> `{"ok": False, "error": "max steps ..."}`.

### `orchestrator/llm.py` (was 30 lines, now 51)
- Line 2: added `from typing import Any`.
- Lines 34-51: NEW `chat(messages, tools=None, timeout_s=120)` - like `ask_llm` but takes the
  full message history and optional tools, and returns the whole assistant message as a dict
  (via `model_dump()`), including `tool_calls` when the model wants a tool.
  `ask_llm` (lines 21-31) is unchanged and still powers `/llm/ping`.
- Effect: the phone now speaks the tool-calling dialect; the agent loop uses it.

### NEW `orchestrator/test_agent.py` (118 lines) - CI-safe fake-brain tests
- Lines 6-18: `_tool_msg()` helper - builds a fake tool-calling message.
- Lines 21-31: `test_answers_without_tools` - model answers immediately -> ok, no steps.
- Lines 33-57: `test_uses_bash_tool` - model requests `ls -la /`, gets a fake result,
  then answers -> 1 tool step recorded.
- Lines 59-87: `test_tag_fallback_when_no_tool_calling` - `<bash>echo hi</bash>` path.
- Lines 89-101: `test_max_steps_guard` - model loops forever -> ok False, "max steps", 10 steps.
- Lines 103-106: `run_agent_sync()` - small helper wrapping `asyncio.run`.
- Key detail: `fake_chat` fakes are **sync** (llm.chat is sync) and `fake_exec` fakes are
  **async** (sandbox_exec is awaited) - mismatching these makes tests explode with
  coroutine errors (learned the hard way, twice).

## Why (the decisions)
- **Why a trace (`steps` list)?** Every action is recorded end-to-end. That's Day 45's
  observability planted early - you can see exactly what the robot did.
- **Why module imports?** Testability (see above).
- **Why MAX_STEPS = 10?** Free-tier models are rate-limited (~50 calls/day); 10 steps is a
  generous ceiling that also prevents infinite loops and cost blowups.
- **Why both tool calling AND tags?** Free OpenRouter models rotate; the loop must keep
  working no matter which model the auto-router picks.
- **Why catch-all with noqa?** Verified: litellm exception hierarchy has no common base.
  A blind catch with an explanation is the correct engineering choice here.

## What changed / what it brings
- The orchestrator can now run an autonomous multi-step agent task with one function call:
  `run_agent("list files and tell me the python version")`.
- No new dependencies (uses `llm.py` + `sandbox.py` + stdlib `json`/`re`).
- Test count: orchestrator now 7 tests (3 API + 4 agent), all CI-safe (no network, no Docker).

## Proof (test run, 9 Aug 2026)
```
$ uv run pytest -q
7 passed, 1 warning in 2.46s

$ uv run ruff check .       -> All checks passed!
$ uv run ruff format --check . -> 7 files already formatted
$ uv run mypy agent.py ...  -> Success: no issues found
```

## What's next (Day 3, Steps 2-5)
- Step 2: expose the loop as `POST /agent/run` in `orchestrator/main.py`
- Step 5: LIVE demo - the robot solves "list files and tell me the Python version" for real,
  using the OpenRouter key and the Docker sandbox.
