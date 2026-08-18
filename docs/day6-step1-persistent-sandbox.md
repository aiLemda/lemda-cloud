# Day 6 - Step 1: Persistent sandbox sessions - one container per agent run

## Goal

Everything an agent does in one run happens in ONE sandbox container: files written in step 1 are visible in step 2, pip installs survive across commands, and the container is destroyed when the run ends. No more fresh-container-per-command (the Day 3 Step 7 gap).

## Problem (from Day 3 Step 7)

`POST /exec` spawned a fresh Docker container per command and removed it after. A two-step demo (pip install requests, then verify) failed: step 2 ran in a brand-new container with nothing from step 1.

## Solution: sessions in the Rust gateway

A session = one long-lived container (`tail -f /dev/null` keep-alive) with the egress proxy env injected at birth. Commands run inside it via `docker exec`. Deleting the session removes the container.

### Rust (`sandbox-gateway`)

1. `src/sessions.rs` (new, 280 lines):
   - `POST /sessions` (`create_session_handler`, line 88) - `docker run -d --name sandbox-session-<id> --network sandbox-net -e HTTP(S)/ALL_PROXY=sandbox-egress:8888 -e NO_PROXY=localhost,127.0.0.1 <image> tail -f /dev/null`; stores `session_id -> container name` in a `tokio::sync::Mutex<HashMap>` shared via axum `State` (line 17: `pub type Sessions`).
   - `POST /sessions/{id}/exec` (`exec_in_session_handler`, line 111) - validates cmd, looks up the container, `docker exec <container> sh -lc <cmd>` with the same output/timeout semantics as `/exec`; on timeout, best-effort `pkill -9 -f` of the hung command inside the session.
   - `DELETE /sessions/{id}` (`delete_session_handler`, line 175) - `docker rm -f` + forget the mapping; unknown session -> 404.
   - Session ids are millis + a process-local atomic counter (`unique_session_id`, line 47), so concurrent runs never collide.
2. `src/exec.rs` - `MAX_CMD_LEN`, `DEFAULT_IMAGE`, `EGRESS_PROXY`, `SANDBOX_NET`, `NO_PROXY` and the default fns become `pub(crate)`; validation extracted into shared `validate_cmd()` used by both `/exec` and session exec (line 40).
3. `src/lib.rs` - routes wired: `POST /sessions`, `POST /sessions/{session_id}/exec`, `DELETE /sessions/{session_id}`; `with_state(Sessions::default())`.

### Python (`orchestrator`)

4. `sandbox.py`:
   - `sandbox_create_session(image=None)` (line 39) - POST `/sessions`, returns `session_id`.
   - `sandbox_close_session(session_id)` (line 52) - DELETE, closes the container.
   - `sandbox_exec(cmd, session_id=None, ...)` (line 18) - when a session is given, posts to `/sessions/{id}/exec`; otherwise keeps the old stateless `/exec` behavior.
5. `agent.py` - `run_agent` now wraps the loop in a session lifecycle: `session_id = await sandbox.sandbox_create_session()` -> run loop in `_run_agent(task, session_id, ...)` -> `finally: await sandbox.sandbox_close_session(session_id)` (lines 48-75). Every `sandbox.sandbox_exec` call passes `session_id=session_id` (lines 104, 120). Session is closed on answer, on max-steps, or on any failure.

## Tests

6. `sandbox-gateway/src/sessions.rs` - 6 new tests (validation x4, map insert/lookup/remove, unique ids). `cargo test`: 10 passed; `cargo clippy -- -D warnings` clean.
7. `orchestrator/test_agent.py`:
   - autouse `fake_session` fixture (line 19) monkeypatches `sandbox.sandbox_create_session`/`close_session` so no test touches Docker or the gateway; CI-safe.
   - `test_session_lifecycle_reused_and_closed` - one session created, every exec used it, closed exactly once.
   - `test_session_closed_even_on_max_steps` - finally-branch fires on the guard path.
   - all exec fakes updated for the `session_id` kwarg.
   - `pytest -q`: 18 passed (16 + 2); ruff + mypy clean.

## Live verification

- Gateway raw: exec 1 writes `step1` to /tmp/persist.txt, exec 2 appends and reads `step1\nstep2` (same container), DELETE -> 204, exec after delete -> 404.
- Full stack through the Bun bridge (streaming): "write `persistent` to /tmp/note.txt, then in a SEPARATE command append ` sandbox` and print it" - 3 live step events (`> /tmp/note.txt`, `>> /tmp/note.txt`, `cat`) then the result with the correct contents. File persisted between separate commands. (Before Day 6: step 2 would find no such file.)
- pip install requests ran INSIDE a session container (verified via /tmp pip build trackers) - the Day 3 Step 7 demo now works.

## Files touched

- `sandbox-gateway/src/sessions.rs` (new)
- `sandbox-gateway/src/lib.rs` (+9 lines)
- `sandbox-gateway/src/exec.rs` (+8/-8 lines, visibility + shared validator)
- `orchestrator/sandbox.py` (+31 lines)
- `orchestrator/agent.py` (+14 lines, session lifecycle)
- `orchestrator/test_agent.py` (+50 lines, fixture + 2 tests)

## Next

- Commit + push + CI green. Then: timeouts on hung sessions, or a `session.timeout` TTL to reap abandoned containers (e.g. gateway crash orphans).