# Astrocyte task runner. CONTRIBUTING, pre-commit, and CI all call these
# targets so local and CI commands never drift.
.DEFAULT_GOAL := help
.PHONY: help install lint typecheck test fmt build docker-build security check

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install Python + web deps and git hooks
	uv sync --all-extras
	cd web && npm ci
	uv run pre-commit install

lint: ## Lint Python and web
	uv run ruff check .
	uv run ruff format --check .
	cd web && npm run lint && npm run format:check

typecheck: ## Type-check Python and web
	uv run mypy src
	cd web && npm run typecheck

test: ## Run Python and web test suites
	uv run pytest
	cd web && npm run test

fmt: ## Auto-format Python and web
	uv run ruff check --fix .
	uv run ruff format .
	cd web && npm run format

build: ## Build the web bundle
	cd web && npm run build

docker-build: ## Build the API image via compose (CI override)
	docker compose -f docker-compose.yml -f docker-compose.ci.yml build

security: ## Audit Python and web dependencies
	uvx pip-audit
	cd web && npm audit --audit-level=high

check: lint typecheck test ## Run all quality gates (lint + types + tests)
