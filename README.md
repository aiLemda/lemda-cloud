# Devin-Clone — a Devin-like AI agent cloud platform (learning build)

An AI software-engineering agent that runs in a sandboxed cloud environment:
a shell, an editor, a browser, git/GitHub, deployment previews, and evals —
all visible and steerable from a web UI.

## Services

| Service | Job | Stack |
|---|---|---|
| `frontend/` | The UI (session, terminal, editor, browser view, approvals) | React 19 + Tailwind 4 + Shadcn (bun) |
| `orchestrator/` | The brain: agent loop, planning, memory, evals | Python 3.11 + FastAPI (uv) |
| `sandbox-gateway/` | The body: PTY bridge, WebSocket fan-out, per-sandbox daemon | Rust + axum + tokio |
| `sandbox-fleet/` | Sandbox lifecycle: containers/microVMs, warm pool, placement | Python + Docker/Firecracker SDKs |
| `infra/` | Postgres, Redis, Mongo, MinIO (S3), egress proxy + docker-compose | Docker Compose |

## How to run (dev)

```bash
cp infra/.env.example infra/.env      # once
make init                             # boot databases + sandbox egress (docker compose up -d)
make dev-orchestrator                 # terminal 1 — API + agent brain (http://localhost:8010)
make dev-gateway                      # terminal 2 — Rust gateway
make dev-fleet                        # terminal 3 — fleet manager
make dev-frontend                     # terminal 4 — UI
```

## Checks

```bash
make test       # all service tests
make ps         # infra health
```

## Docs

See `docs/` — the full theory curriculum (7 parts, 51 chapters) that drives this build:
foundations, sandbox isolation, tools, platform architecture, evals, security, build plan.
