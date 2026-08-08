.PHONY: up down logs ps test dev-orchestrator dev-gateway dev-fleet dev-frontend init

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
init: up
	@echo "Databases ready. Create infra/.env from infra/.env.example first."

# --- Dev servers (one per service, run in separate terminals) ---
dev-orchestrator:
	cd orchestrator && uv run uvicorn main:app --reload --port 8000

dev-gateway:
	cd sandbox-gateway && cargo run

dev-fleet:
	cd sandbox-fleet && uv run python main.py

dev-frontend:
	cd frontend && bun dev

# --- Tests (all services) ---
test:
	cd orchestrator && uv run pytest -q
	cd sandbox-fleet && uv run pytest -q
	cd sandbox-gateway && cargo test
	cd frontend && bun run build
