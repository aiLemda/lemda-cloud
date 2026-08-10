.PHONY: up down logs ps test dev-orchestrator dev-gateway dev-fleet dev-frontend init egress-up egress-down egress-logs

# --- Infra (databases, object storage) ---
up:
	docker compose -f infra/docker-compose.yml --env-file infra/.env up -d
	@echo "Infra up: postgres:5432 redis:6379 mongo:27017 minio:9000/9001"

down:
	docker compose -f infra/docker-compose.yml --env-file infra/.env down

logs:
	docker compose -f infra/docker-compose.yml --env-file infra/.env logs -f

ps:
	docker compose -f infra/docker-compose.yml --env-file infra/.env ps

# --- First-time setup ---
init: up egress-up
	@echo "Databases ready. Create infra/.env from infra/.env.example first."

# --- Sandbox egress (internal network + allowlisted proxy, Ch 12 golden rule) ---
egress-up:
	docker network inspect sandbox-net >/dev/null 2>&1 || docker network create --internal sandbox-net
	docker build -q -t sandbox-egress infra/egress
	docker rm -f sandbox-egress 2>/dev/null || true
	docker run -d --name sandbox-egress --network bridge sandbox-egress >/dev/null
	docker network connect sandbox-net sandbox-egress
	@echo "Egress proxy up: sandbox-egress on :8888 (allowlist: GitHub, PyPI, npm)"

egress-down:
	docker rm -f sandbox-egress 2>/dev/null || true

egress-logs:
	docker logs -f sandbox-egress

# --- Dev servers (one per service, run in separate terminals) ---
dev-orchestrator:
	cd orchestrator && uv run uvicorn main:app --reload --port 8000

dev-gateway:
	cd sandbox-gateway && cargo run

dev-fleet:
	cd sandbox-fleet && uv run uvicorn main:app --reload --port 8011

dev-frontend:
	cd frontend && bun dev

# --- Tests (all services) ---
test:
	cd orchestrator && uv run pytest -q
	cd sandbox-fleet && uv run pytest -q
	cd sandbox-gateway && cargo test
	cd frontend && bun run build
