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

## Follow-up (same day): fleet health endpoint

7. `GET /sessions/stats` (`stats_handler`, line ~230) - `{"live_sessions": N, "live_containers": M, "stale_containers": K}`: map size + best-effort docker counts (`docker ps -a --filter name=sandbox-session-`); docker counts are `null` when docker is unreachable. Two new unit tests (`stats_reflects_live_sessions`, `stats_zero_when_no_sessions`); `cargo test`: 17 passed.

Live-verified: 2 sessions -> `2/2/0`, delete one -> `1/1/0`, delete other -> `0/0/0`.

## Files touched

- `sandbox-gateway/src/sessions.rs` (+110/-10 lines)
- `sandbox-gateway/src/lib.rs` (+8 lines, reaper + stats wiring)

## Next

- Commit + push + CI green. Natural follow-ups: session listing/debug endpoint, per-run limits, or a health endpoint reporting live container count.