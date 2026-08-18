# Day 7 - Step 1: Session TTL reaper - no more orphaned sandboxes

## Goal

Sandbox containers must not outlive their purpose. If the orchestrator dies mid-run or the gateway crashes and restarts, the `tail -f /dev/null` keep-alive containers would run forever. Day 7 adds a background reaper: idle sessions are removed after a TTL, and containers orphaned by a gateway restart are swept on boot.

## Problem

`sandbox-gateway/src/sessions.rs` tracked sessions only in memory. A `kill -9` of the gateway lost the map but left the docker containers running. Nothing ever cleaned them.

## Solution (all in `sandbox-gateway/src/sessions.rs`)

1. `SessionEntry { container, last_used: Instant }` (line 17) - every session now records when a command last ran inside it. `Sessions` becomes `Arc<Mutex<HashMap<String, SessionEntry>>>`.
2. `last_used` is set at creation (line ~210) and touched on every exec (line ~135) - a busy agent run never gets reaped.
3. `expired_ids(entries, ttl)` (line 69) - pure helper returning ids idle >= TTL; unit-tested.
4. `reap_pass(sessions, ttl)` (line 78) - the sweep, run on every tick:
   - removes docker containers for expired sessions, then
   - lists ALL `sandbox-session-*` containers via `docker ps -a --filter name=sandbox-session-` and removes any not managed by the live map (stale containers from a previous gateway lifetime). If docker is unavailable (tests/CI) it silently skips.
5. `start_reaper(sessions)` (line 128) - `tokio::spawn` loop with `tokio::time::interval`; configurable via env: `SANDBOX_SESSION_TTL_SECS` (default 900 = 15 min) and `SANDBOX_REAP_INTERVAL_SECS` (default 30). First tick fires immediately, so a fresh boot immediately sweeps crash orphans.
6. `app()` in `src/lib.rs` (line 15) - creates the shared `Sessions`, calls `start_reaper`, and passes the same Arc to `with_state`.

Semantics: sessions do not survive gateway restarts - the orchestrator's run is dead anyway, so its containers are garbage.

## Tests

- `expired_ids_only_returns_idle_sessions` - stale (100s idle) vs fresh entry with 30s TTL.
- `expired_ids_empty_for_empty_map`.
- `session_map_insert_lookup_remove` updated for `SessionEntry`.
- `cargo test`: 15 passed (12 lib + 2 integration + 1 doc); `cargo clippy -- -D warnings`: clean.

No Python/frontend changes - the orchestrator API is untouched.

## Live verification

1. Crash simulation: create session -> `kill -9` the gateway (container orphaned) -> restart -> the boot sweep removed the orphan; exec on the dead session -> 404.
2. TTL: gateway started with `SANDBOX_SESSION_TTL_SECS=5 SANDBOX_REAP_INTERVAL_SECS=2`; 4 execs 3s apart kept the session alive (touch works); after 5s idle the container vanished and exec -> 404.
3. Regression with defaults (900s TTL): full streaming agent run ("create /tmp/ok.txt, read it back") - 2 live steps + correct answer, session closed by the orchestrator as usual.

## Follow-up (same day): fleet health endpoint + capacity cap + UI chip

7. `GET /sessions/stats` (`stats_handler`) - `{"live_sessions": N, "max_sessions": M, "live_containers": K, "stale_containers": L}`: map size + capacity + best-effort docker counts; docker counts `null` when docker unreachable.
8. Fleet cap: `SANDBOX_MAX_SESSIONS` (default 8); creation past the cap -> `429 session capacity reached (N live sessions) - retry later`. Checked before any docker work, so a runaway agent loop can't exhaust the host.
9. UI: bridge route `/api/sessions/stats` (`frontend/src/index.ts`, `BUN_GATEWAY_URL` default `http://127.0.0.1:8080`), `fetchSessionStats()` in `client.ts`, `SessionStats` type, and a live `🐳 N sandboxes` chip in the App header polling every 5s.

Tests: `capacity_respected`, `max_sessions_env_override`, stats assert `max_sessions`; `cargo test`: 19 passed. Live-verified: cap=3 -> 3 creates 200, 4th 429, stats `3/3/3/0`; cleanup -> `0/3/0/0`; default restart -> `0/8`; bridge + full agent run green.

## Files touched

- `sandbox-gateway/src/sessions.rs` (+130/-15 lines)
- `sandbox-gateway/src/lib.rs` (+8 lines, reaper + stats wiring)
- `frontend/src/index.ts` (+15 lines, stats bridge route)
- `frontend/src/lib/agent.ts` (+8 lines, `SessionStats`)
- `frontend/src/lib/client.ts` (+24 lines, `fetchSessionStats`)
- `frontend/src/App.tsx` (+17 lines, live sandbox chip)

## Next

- Commit + push + CI green. Natural follow-ups: session listing/debug endpoint, per-run limits, or a health endpoint reporting live container count.