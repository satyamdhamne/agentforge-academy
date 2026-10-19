# Convenience targets. See README.md for the full guide.
DB_URL ?= postgresql+psycopg://agentforge:agentforge@localhost:5432/agentforge

.PHONY: up down logs install test test-agents test-sandbox test-backend test-frontend e2e lint verify-content seed dev-api dev-sandbox dev-web

up:            ## Full stack in Docker (http://localhost:8080)
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f backend sandbox

install:       ## Local dev dependencies
	python -m pip install -e "./agents[dev,pdf]" -e "./backend[dev]" -e "./sandbox[dev]"
	cd frontend && npm ci

test: test-agents test-sandbox test-backend test-frontend verify-content
test-agents:
	cd agents && python -m pytest -q
test-sandbox:
	cd sandbox && python -m pytest -q
test-backend:  ## needs PostgreSQL (TEST_DATABASE_URL, default agentforge_test on localhost)
	cd backend && python -m pytest -q
test-frontend:
	cd frontend && npm run typecheck && npm test
verify-content:
	python scripts/verify_content.py
e2e:           ## needs the stack running (make up, or the dev servers)
	cd frontend && E2E_BASE_URL=$${E2E_BASE_URL:-http://localhost:8080} npx playwright test
lint:
	ruff check agents backend sandbox scripts

seed:
	cd backend && DATABASE_URL=$(DB_URL) python -m alembic upgrade head && DATABASE_URL=$(DB_URL) python -m app.seed
dev-sandbox:   ## runner on :8080 (TEST/DEV ONLY outside Docker: no container isolation)
	cd sandbox && SANDBOX_TOKEN=devtoken uvicorn runner.app:app --port 8080
dev-api:
	cd backend && DATABASE_URL=$(DB_URL) SANDBOX_URL=http://127.0.0.1:8080 SANDBOX_TOKEN=devtoken uvicorn app.main:app --reload --port 8000
dev-web:
	cd frontend && npm run dev
