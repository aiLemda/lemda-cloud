# Step 2 - Sandbox v0: POST /exec with egress allowlist (Ch 12 golden rule)

The first real sandbox capability: run a command inside an isolated Docker container from the Rust gateway, where the container can ONLY reach GitHub, PyPI, and npm (the golden rule: allow only what an agent needs to code).

## Why this design (Ch 12)

Two-layer enforcement - neither layer alone is enough:

1. **Layer 1 - kernel: `sandbox-net` is an `--internal` Docker network.** Containers on it have NO route to the internet and, as verified empirically, Docker's embedded DNS does not forward external names on internal networks (`socket.gaierror: Temporary failure in name resolution`). Direct escape attempts fail at the DNS/routing level.
2. **Layer 2 - application: allowlisted CONNECT proxy.** The only machine that is dual-homed (internal net + internet) is `sandbox-egress`. npm/pip/curl/git are pointed at it via HTTPS_PROXY. The proxy accepts CONNECT only for allowlisted hostnames (exact-match, so `evil-github.com` is not a bypass). Everything else gets `403 Forbidden`.

The egress proxy must be dual-homed because Docker Desktop on macOS runs containers inside a Linux VM - host-level iptables rules are not manageable from the Mac. This is the standard approach (corporate proxies, E2B-style sandboxes).

## What changed, file by file (with line ranges)

### NEW `infra/egress/proxy.py` (149 lines)
- Lines 5-21: `ALLOWED_HOSTS` frozenset - GitHub family (github.com, api.github.com, codeload.github.com, raw.githubusercontent.com, objects.githubusercontent.com, uploads.github.com, githubassets.com), PyPI family (pypi.org, www.pypi.org, files.pythonhosted.org, pypi.io), npm family (registry.npmjs.org, www.npmjs.com, npmjs.org, nodejs.org).
- Lines 61-88: `CONNECT` handling (HTTPS/TLS tunnel). Checks hostname against the allowlist -> `HTTP/1.1 200 Connection established` and byte-pipes the tunnel, or `403 Forbidden`.
- Lines 89-111: absolute-URI forwarding for plain HTTP requests, same allowlist check.
- Lines 113-132: connection pump with 120s idle timeout.
- Lines 134-145: async server on `0.0.0.0:8888` with a decision log (`ALLOW`/`BLOCK` per peer).
- Effect: every egress attempt is logged and either tunneled to an allowlisted host or refused.

### NEW `infra/egress/Dockerfile` (5 lines)
- `FROM python:3.12-slim`, copies proxy.py, exposes 8888.
- Effect: the proxy is its own tiny container image.

### `Makefile`
- Line 1: added `egress-up egress-down egress-logs` to `.PHONY`.
- Line 18: `init: up` -> `init: up egress-up` (first-time setup now boots the sandbox egress too).
- Lines 21-28: NEW `egress-up` - creates `sandbox-net` (`--internal`) if missing, builds the proxy image, starts `sandbox-egress` on the default bridge, then connects it to `sandbox-net` (dual-homed).
- Lines 30-31: NEW `egress-down` - removes the proxy container.
- Lines 33-34: NEW `egress-logs` - live proxy decision log.

### `sandbox-gateway/Cargo.toml`
- Line 8: `serde = "1.0.229"` -> `serde = { version = "1.0.229", features = ["derive"] }`
- Effect: `#[derive(Serialize, Deserialize)]` on request/response types (this was the compile error: serde's derive macros need the `derive` feature).

### NEW `sandbox-gateway/src/exec.rs` (161 lines)
- Lines 17-27: `ExecRequest` - `cmd`, optional `image` (default `python:3.12-slim`), optional `timeout_s` (default 30).
- Lines 30-36: `ExecResult` - `exit_code`, `stdout`, `stderr`, `timed_out`, `duration_ms`.
- Lines 38-47: `validate()` - rejects empty cmd, cmd > 4096 chars, timeout outside 1-120s.
- Lines 49-100: `run_exec()` - spawns `docker run --rm --name sandbox-exec-<millis> --network sandbox-net -e HTTPS_PROXY/HTTP_PROXY/ALL_PROXY=http://sandbox-egress:8888 -e NO_PROXY=localhost,127.0.0.1 <image> sh -lc "<cmd>"`; waits with a tokio timeout; on timeout runs `docker kill <name>` (the `--rm` flag then removes it).
- Lines 111-147: `spawn_sandbox()` builds the docker args incl. the proxy env vars that make npm/pip/curl use the allowlisted egress.
- Lines 149-161: unit tests for `validate()` (empty, too long, bad timeout, valid).

### `sandbox-gateway/src/lib.rs` (rewritten, 24 lines)
- Lines 1-3: `mod exec;`
- Line 10: router now has `POST /exec` in addition to `GET /healthz`.
- Lines 17-23: `exec_handler` - JSON body -> validate (422 on invalid) -> `run_exec()` -> JSON result.

### NEW `sandbox-gateway/tests/exec.rs` (37 lines)
- Two integration tests against the axum app: empty cmd -> 422, timeout 999 -> 422. No Docker needed, so CI-safe.

### `README.md`
- Line 15: infra row now mentions the egress proxy.
- Line 21: `make init` comment notes it boots sandbox egress too.

## What was used
- **Docker**: `--internal` network (kernel-level isolation), `docker network connect` for dual-homing, `docker run --rm` for throwaway sandboxes, `docker kill` for timeout enforcement.
- **Python asyncio**: 100-line CONNECT proxy with an exact-match hostname allowlist.
- **Rust**: axum 0.8 (`POST /exec` handler), tokio (`Command` + `timeout`), serde derive.
- **Verified fact**: Docker internal networks do NOT forward external DNS (tested live before designing around it).

## Proof (real output, 9 Aug 2026)

```
POST /exec {"cmd":"echo hello && pwd && whoami"}
  -> {"exit_code":0,"stdout":"hello\n/\nroot\n","duration_ms":241}

POST /exec {"cmd":"python ... urlopen('https://api.github.com/zen')"}
  -> {"exit_code":0,"stdout":"Encourage flow.\n"}     # ALLOWED through proxy

POST /exec {"cmd":"python ... urlopen('https://example.com')"}
  -> exit_code 1, stderr "... Tunnel connection failed: 403 Forbidden"   # BLOCKED

POST /exec {"cmd":"sleep 5","timeout_s":1}
  -> {"timed_out":true,"stderr":"command timed out - sandbox container killed"}

POST /exec {"cmd":"pip install --dry-run --quiet requests ..."}
  -> exit_code 0                                          # pypi ALLOWED

docker logs sandbox-egress:
  ALLOW  CONNECT api.github.com:443
  BLOCK  CONNECT example.com:443
  ALLOW  CONNECT pypi.org:443
  ALLOW  CONNECT files.pythonhosted.org:443
```

## Test suite
`cargo test` -> 7 passed (4 unit validation + 2 exec API + 1 healthz).

## Known v0 limits (honest)
- Allowlist is exact-hostname; CDN redirect hosts may need additions later (monitor `docker logs sandbox-egress` BLOCK lines).
- Egress enforcement is at the proxy + internal network; kernel-level per-connection filtering is the Firecracker-phase upgrade (Ch 32-40).
- The command runs as root in the container (agent-level hardening comes with the real sandbox in Day 2-3).

## Next step
Day 3: orchestrator agent loop - LLM thinks -> calls `POST /exec` -> reads result -> loops (first real Devin-style agent).
