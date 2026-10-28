# Shortcuts for the common tasks. On Windows, run the scripts under deploy/scripts with Git Bash.
.PHONY: install dev-api dev-floor dev-web test lint images up down cluster-up cluster-down manifests

install:
	uv sync --all-groups
	npm --prefix apps/web install

dev-api:
	DEMO_MODE=true uv run uvicorn gauntlet.api:app --port 8000 --reload

dev-floor:
	DEMO_MODE=true uv run -m gauntlet.trading_floor

dev-web:
	npm --prefix apps/web run dev

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check . && uv run pyright
	npm --prefix apps/web run lint && npm --prefix apps/web run typecheck

images:
	docker compose build

up:
	docker compose up --build -d
	@echo "Gauntlet: http://localhost:3000"

down:
	docker compose down

cluster-up:
	deploy/scripts/cluster-up.sh

cluster-down:
	deploy/scripts/cluster-down.sh

manifests:
	helm lint --strict deploy/helm/gauntlet -f deploy/helm/gauntlet/values-local.yaml
	helm lint --strict deploy/helm/gauntlet -f deploy/helm/gauntlet/values-prod.yaml
