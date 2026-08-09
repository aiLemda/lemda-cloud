# Step 3 - End-to-end chain: orchestrator -> gateway -> sandbox (first agent action)

The first real agent action: the orchestrator (the "brain") sends a command through the Rust gateway (the "body") into the isolated Docker sandbox, and the output comes all the way back. Verified live with `ls`, a custom command, and a GitHub egress call.

## The chain (what happens on one request)

```
curl /sandbox/ls
  -> orchestrator (FastAPI :8010)  sandbox.py -> httpx POST
  -> sandbox-gateway (Rust :8080)  /exec handler -> docker run
  -> sandbox-net (--internal network)
  -> python:3.12-slim container   sh -lc "ls -la /"
  -> stdout captured -> JSON back through gateway -> orchestrator -> curl
```

## What changed, file by file (with line ranges)

### NEW `orchestrator/sandbox.py` (22 lines) - the gateway client
- Lines 1-5: imports; `REPO_ROOT`/`ENV_FILE` resolved from `__file__` so `infra/.env` is found from any working directory (same pattern as `llm.py`).
- Lines 7-11: `GatewaySettings` (pydantic-settings) - reads `GATEWAY_URL`, default `http://127.0.0.1:8080`.
- Lines 13-22: `sandbox_exec(cmd, image=None, timeout_s=30)` - async httpx POST to `{gateway_url}/exec` with `{cmd, image?, timeout_s}`; raises on non-2xx; returns the parsed `ExecResult` dict (`exit_code`, `stdout`, `stderr`, `timed_out`, `duration_ms`).
- Effect: the orchestrator now has one function that reaches the sandbox. Day 3's agent loop calls exactly this.

### `orchestrator/main.py` (rewritten, 38 lines)
- Lines 1-5: imports add `HTTPException`, `BaseModel`, and `sandbox_exec` from the new module.
- Lines 10-13: `ExecRequest` model (`cmd` required, optional `image`, optional `timeout_s` default 30).
- Lines 28-33: NEW `POST /sandbox/exec` - passthrough endpoint; forwards to the gateway, maps failures to 502 `gateway call failed: ...`.
- Lines 36-38: NEW `GET /sandbox/ls` - the canonical demo: `sandbox_exec("ls -la /")`. One curl returns a full sandbox directory listing.
- Effect: the sandbox is now reachable over the orchestrator's HTTP API - the same API the UI and the agent loop will use.

### `orchestrator/test_main.py` (rewritten, 40 lines)
- Lines 15-29: `test_sandbox_ls_wiring` - monkeypatches `main.sandbox_exec` with a fake result, asserts `/sandbox/ls` returns it (CI-safe: no Docker needed).
- Lines 32-40: `test_sandbox_exec_gateway_down` - fake raises `httpx.ConnectError`, asserts 502 with the right detail.
- Effect: the new endpoints are regression-protected without requiring a live gateway in CI.

### `infra/.env` (gitignored)
- Line 26-27: NEW `GATEWAY_URL=http://127.0.0.1:8080`.

### `infra/.env.example` (committed template)
- Lines 26-27: same `GATEWAY_URL` line with the comment `orchestrator -> gateway -> container`.

## What was used
- **httpx** (async client, already a dep) for the orchestrator -> gateway hop.
- **pydantic-settings** for `GATEWAY_URL` (same `.env` pattern as `llm.py`).
- **pytest + TestClient + monkeypatch** for CI-safe endpoint tests.

## Proof (real output, 9 Aug 2026)

```
$ curl http://127.0.0.1:8010/sandbox/ls
{"exit_code":0,"stdout":"total 56\ndrwxr-xr-x   1 root root 4096 Aug  9 16:55 .\n...
drwxr-xr-x   1 root root 4096 Aug  3 00:00 usr\ndrwxr-xr-x   1 root root 4096 Aug  3 00:00 var\n",
 "stderr":"","timed_out":false,"duration_ms":494}

$ curl -X POST .../sandbox/exec -d '{"cmd":"echo chained-from-orchestrator && python3 --version"}'
{"exit_code":0,"stdout":"chained-from-orchestrator\nPython 3.12.13\n","duration_ms":652}

$ curl -X POST .../sandbox/exec -d '{"cmd":"python ... urlopen('https://api.github.com/zen')"}'
{"exit_code":0,"stdout":"github zen: Speak like a human.\n","duration_ms":4338}
```

The third test proves the whole stack including egress: orchestrator -> gateway -> sandbox -> proxy -> GitHub -> back.

## Test suite (full monorepo)
```
orchestrator: 3 passed | fleet: 1 passed | gateway: 7 passed
```
(`make test` - all green, including clippy-clean cargo build.)

## Notes / next step
- `/sandbox/ls` has no try/except yet (returns 500 if gateway is down); `POST /sandbox/exec` returns 502. Error middleware comes with the agent loop.
- Day 3: the real agent loop - LLM thinks (via `llm.py`) -> calls `sandbox_exec` -> reads stdout -> loops until done. That is the first Devin-style agent.
