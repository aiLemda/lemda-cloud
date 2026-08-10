# Day 3 — Step 4: Tests that need no AI (`orchestrator/test_agent.py`)

## Topic

The agent loop must be testable **without any AI** — no API key, no network,
no Docker. Step 4 is the test suite that proves the loop's behavior by
swapping the real brain (LLM) and hands (sandbox) for scripted fakes.

## What I did

A monkeypatched **fake brain** (`llm.chat`) plus a **fake hand**
(`sandbox.sandbox_exec`) drive `run_agent` in 4 offline tests:

1. **Answers immediately** (`test_agent.py:22-34`) — fake brain replies
   `<answer>42</answer>` on the first turn. Asserts `ok`, `answer == "42"`,
   `steps == []` (no tool was ever needed).
2. **Uses the tool** (`test_agent.py:37-66`) — fake brain emits a real
   `tool_calls` entry on turn 1 (via the `_tool_msg` helper, `:8-19`), then
   `<answer>files listed</answer>` on turn 2. Fake hand executes `ls -la /`.
   Asserts the tool result landed in `steps[0]` with the right `cmd`.
3. **`<bash>` tag fallback** (`test_agent.py:69-101`) — fake brain ignores tool
   calling and answers in plain text with `<bash>echo hi</bash>`; the loop must
   parse the tag and still execute the command. Asserts `steps[0]["cmd"] == "echo hi"`.
4. **Never finishes → max-steps guard** (`test_agent.py:103-121`) — fake brain
   loops forever issuing tool calls. Asserts `ok is False`, error mentions
   "max steps", and exactly `MAX_STEPS` steps were recorded (no infinite loop).

`run_agent_sync` (`:124-125`) wraps the async loop in `asyncio.run` so tests
stay plain sync functions.

## Why

- **CI-safe by construction:** the loop's only two I/O boundaries are
  monkeypatched in every test — the imports are just `asyncio`, `json`,
  `typing` and `agent`. No `httpx` socket ever opens, no Docker container ever
  starts, no key needed. Tests run anywhere, in seconds, for free.
- **Deterministic:** the fake brain always behaves the same, so the loop's
  logic (tool-call routing, tag fallback, guard rails) is tested in
  isolation — exactly what you can't get from a real, flaky model.
- **Guard rail proven:** the max-steps test pins the loop's one real safety
  property — a runaway model cannot run forever.

## What change it brings

- `pytest` now validates the core loop offline: 4 tests, ~0 API cost, 0
  network calls, 0 Docker calls.
- Any future edit to the loop (new tool, different prompt, guard changes) is
  caught in seconds without touching the wallet.
- This is the seed of the project's test discipline: fakes at the boundaries,
  real integrations proven separately with 1-2 live calls.

## Where (file → lines)

| File | Lines | Change |
|---|---|---|
| `orchestrator/test_agent.py` | 1-5 | imports (loop constants + stdlib only) |
| `orchestrator/test_agent.py` | 8-19 | `_tool_msg` fake assistant tool-call message |
| `orchestrator/test_agent.py` | 22-34 | test: immediate answer, no tools |
| `orchestrator/test_agent.py` | 37-66 | test: real tool call → result in steps |
| `orchestrator/test_agent.py` | 69-101 | test: `<bash>` tag fallback path |
| `orchestrator/test_agent.py` | 103-121 | test: max-steps guard fires |
| `orchestrator/test_agent.py` | 124-125 | `run_agent_sync` async wrapper |

Verified: `pytest` — 13 passed total, including these 4, with no network or
Docker involved (all boundaries monkeypatched).
