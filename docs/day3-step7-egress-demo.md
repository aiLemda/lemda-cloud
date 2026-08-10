# Day 3 — Step 7: Egress demo — the brain uses the allowlist by itself

## Topic

Stretch demo: prove the loop can install real software from the internet —
`pip install requests` through the sandbox egress proxy — entirely on the
model's own initiative. The sandbox's only exit to the internet is the egress
proxy (`infra/egress/proxy.py`) with a hard allowlist (GitHub, PyPI, npm).

## What I did

Started gateway + orchestrator, POSTed a task to `/agent/run` that asked for a
pip install and a verification, twice.

**Run 1 — naive task** (install, then verify in a separate command):

```
STEP 1 -> tool: pip install requests                      exit 0, 11062 ms
          (downloaded requests-2.34.2 + urllib3, idna, charset_normalizer, certifi from PyPI)
STEP 2 -> tool: python3 -c "import requests; ..."          exit 1, 1210 ms
          ModuleNotFoundError: No module named 'requests'
```

The install worked through the allowlist. But verification failed — and the
**robot diagnosed why**: "each `run_bash` invocation runs in a separate shell
session, so the package installation does not persist between commands… use
`pip install requests && python3 -c …` in the same command."

**Run 2 — combined command** (the robot's own suggested fix):

```
STEP 1 -> tool: pip install requests && python3 -c "import requests; print(requests.__version__)"
          exit 0, 10302 ms
          Successfully installed certifi-2026.7.22 charset_normalizer-3.4.9 idna-3.18 requests-2.34.2 urllib3-2.7.0
          2.34.2
```

## Why

- **Egress allowlist proven, not just documented:** the downloaded wheels
  crossed only the allowlisted PyPI hosts (pypi.org / files.pythonhosted.org)
  via `HTTP(S)_PROXY=http://sandbox-egress:8888`, which the gateway injects
  into every exec container (`sandbox-gateway/src/exec.rs:119-126`).
- **The brain navigated it alone:** it chose pip, hit PyPI, verified the
  import, found the failure, reasoned about the root cause, and fixed its own
  approach — the full loop, zero human steering.
- **Found a real product gap:** every `run_bash` runs in a **fresh container**
  — state doesn't persist between steps. Fine for read-only tasks (the Step 5
  demos), a blocker for real work (install → use). That's a future session
  (persistent sandbox per agent run) — noted here so it isn't lost.

## What change it brings

- No code changed — proof step.
- Reproducible demo that the sandbox has real, controlled internet and the
  agent can use it end to end.
- Known-limitation logged: ephemeral per-command sandbox → persistence needed
  before the agent can "install then build" across steps.

## Where (file → lines)

| File | Lines | Change |
|---|---|---|
| — | — | no code changes; live runs only |

(For context: the allowlist lives at `infra/egress/proxy.py:3-24`; the proxy
injection at `sandbox-gateway/src/exec.rs:119-126`.)

## Verified

- Run 1: pip reached PyPI through the allowlist (exit 0), verification hit the
  ephemeral-container gap; model diagnosed correctly.
- Run 2: install + verify in one command → exit 0, `2.34.2` printed.
- Cost: 4 LLM calls, free tier.
