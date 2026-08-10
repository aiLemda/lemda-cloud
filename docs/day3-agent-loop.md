# Day 3 — Agent loop: line-level report

Standing-rule report: what, why, what changed, and exactly where (file:lines).

## What

Built the agent's brain (the loop), upgraded the LLM "phone", exposed the loop
as an HTTP API, pinned it with AI-free tests, and proved it live. The system
now goes: task → model thinks → real tool call in a Docker sandbox → answer —
all visible step by step.

## Why

- **The loop is the product:** everything after this (sessions, tools, memory,
  the frontend) hangs off `run_agent`. Day 3 made it real and testable.
- **Resilience planted early:** fallback provider (Gemini/etc.) if OpenRouter
  dies; `achat` keeps the event loop responsive; max-10-step guard is the
  robot's seatbelt.
- **Traceability = future observability:** every step is returned in the API
  response — Day 45's replays, forked from Day 3's JSON.

## What changed (file → lines)

### `orchestrator/agent.py` (new, 111 lines) — the loop
| Lines | Content |
|---|---|
| 8 | `MAX_STEPS = 10` guard |
| 10-18 | system prompt: sandbox rules, tool, `<answer>`/`<bash>` contract |
| 20-33 | `run_bash` tool schema |
| 36-45 | `_summarize`: command output → short context for the model |
| 48-111 | `run_agent`: message loop, tool execution, `<bash>` fallback, `<answer>` extraction, max-steps return |

### `orchestrator/llm.py` (edited) — the phone
| Lines | Content |
|---|---|
| 1 | `asyncio` import |
| 21-23 | fallback provider settings (`LLM_FALLBACK_*`) |
| 26-43 | `_completion` (shared provider call) |
| 59-88 | `chat`: full message with `tool_calls` + automatic fallback |
| 91-96 | `achat`: async twin, runs LLM call off the event loop |
| 46-56 | `ask_llm` unchanged (ping) |

### `orchestrator/main.py` (edited) — the door
| Lines | Content |
|---|---|
| 5 | `from agent import run_agent` |
| 18-19 | `AgentRunRequest {task}` |
| 47-51 | `POST /agent/run`: 422 on empty task, else run and return `{ok, answer, steps}` |

### Tests (new) — no AI, no network, no Docker
| File | Lines | Covers |
|---|---|---|
| `test_agent.py` | 22-34 | immediate answer (0 tools) |
| `test_agent.py` | 37-66 | real tool call → step recorded |
| `test_agent.py` | 69-101 | `<bash>` tag fallback |
| `test_agent.py` | 103-121 | max-steps guard fires |
| `test_llm.py` | 1-81 | fallback routing + achat (4 tests) |
| `test_agent_api.py` | 1-29 | `/agent/run` wiring + 422 |

### Docs (new)
| File | Topic |
|---|---|
| `docs/day3-step1-agent-loop.md` | step 1 report |
| `docs/day3-step2-llm-upgrade.md` | step 2 report |
| `docs/day3-step3-agent-run.md` | step 3 report |
| `docs/day3-step4-agent-tests.md` | step 4 report |
| `docs/day3-step5-live-demo.md` | live demo + reproduce |
| `docs/day3-agent-loop.md` | this report |

## Verified

- `ruff check` / `ruff format --check` — clean
- `mypy` — clean
- `pytest` — **13 passed** (no network, no Docker)
- Live (Step 5): 2-step tool run (`ls -la /` → `python3 --version` → answer)
  and 0-tool run (`2+2` → `4`); 4 free-tier calls
- CI (GitHub Actions): orchestrator ruff+mypy+pytest, gateway clippy+test,
  frontend build

## How it works in one sentence

`POST /agent/run` takes a task; `run_agent` loops: model (via `llm.achat`)
thinks → if it asks, `sandbox.sandbox_exec` runs the command in the Docker
sandbox and the result is fed back → until an `<answer>` appears or the
10-step guard trips; every tool call is kept in `steps[]` and returned as-is.
