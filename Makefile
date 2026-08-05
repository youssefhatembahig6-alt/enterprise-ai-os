### Enterprise AI OS — the two documented commands are `make up` and `make reset`.
### Everything else supports them. See docs/README or specs/.../quickstart.md.

COMPOSE := docker compose -f infrastructure/docker-compose.yml --env-file .env
SEED    := $(COMPOSE) run --rm --no-deps -T seed

.DEFAULT_GOAL := help
.PHONY: help up down reset seed verify fingerprint migrate test test-unit \
        test-integration test-security test-e2e lint fmt contracts docs docs-check \
        test-site logs ps clean

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.env:
	@cp infrastructure/.env.example .env
	@echo "Created .env from infrastructure/.env.example"

## --------------------------------------------------------------------------
## The two documented commands (spec FR-002, FR-004)
## --------------------------------------------------------------------------

up: .env ## Start the complete local system and wait until healthy
	$(COMPOSE) up -d --build
	@echo "Waiting for services to become healthy..."
	@bash infrastructure/wait-for-healthy.sh
	$(COMPOSE) run --rm --no-deps -T api alembic upgrade head
	@echo ""
	@echo "  Ready.  API http://localhost:8000   Site http://localhost:3000"
	@echo "  Next:   make seed"

reset: .env ## DESTROY all local data and regenerate the full dataset
	@echo "This destroys every row, object, vector, and cache entry in the local environment."
	@read -p "Type 'reset' to continue: " ans; [ "$$ans" = "reset" ] || (echo "Aborted."; exit 4)
	# No `alembic upgrade` here: per contracts/seed-cli.md, `reset` re-runs migrations
	# itself after truncating. Running them twice was harmless but misleading about
	# where the responsibility lives.
	$(SEED) reset --yes

## --------------------------------------------------------------------------
## Supporting commands
## --------------------------------------------------------------------------

down: ## Stop all services, keep volumes
	$(COMPOSE) down

clean: ## Stop all services AND delete volumes
	$(COMPOSE) down -v

seed: ## Populate an empty environment (refuses if not empty)
	$(SEED) seed

verify: ## Recompute the fingerprint and run all integrity checks
	$(SEED) verify

fingerprint: ## Print the current dataset fingerprint
	$(SEED) fingerprint

migrate: ## Apply database migrations
	$(COMPOSE) run --rm --no-deps -T api alembic upgrade head

logs: ## Tail service logs
	$(COMPOSE) logs -f

ps: ## Show service status
	$(COMPOSE) ps

contracts: ## Regenerate TypeScript API types from the OpenAPI schema
	pnpm --filter @eaios/contracts generate

contracts-check: ## Fail if the committed API types no longer match the running API
	pnpm --filter @eaios/contracts verify

docs: ## Regenerate docs/personas.md and docs/dataset.md from the generator
	uv run python -m eaios_seed.cli docs

docs-check: ## Fail if the committed docs no longer match the dataset
	uv run python -m eaios_seed.cli docs --check

## --------------------------------------------------------------------------
## Tests — the order CI runs them in
## --------------------------------------------------------------------------

test: test-unit test-integration test-security test-e2e ## Run the full suite

test-unit: ## Fast, no external services
	uv run pytest tests/unit -m unit

test-integration: ## Requires the running stack
	uv run pytest tests/integration -m integration

test-security: ## Tenant isolation and access-control invariants
	uv run pytest tests/security -m security

test-e2e: ## Full clean-environment lifecycle
	uv run pytest tests/e2e -m e2e

test-site: ## Public website: components, accessibility, responsive, metadata
	pnpm --filter @eaios/web test
	pnpm --filter @eaios/web exec playwright test

lint: ## Lint Python and TypeScript
	uv run ruff check .
	uv run mypy packages/core/src apps/api/src scripts/seed/src services/worker/src
	pnpm lint

fmt: ## Format everything
	uv run ruff format .
	pnpm format
