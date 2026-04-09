.DEFAULT_GOAL := help
SHELL := /bin/bash

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------
PYTHON  := uv run python
UVICORN := uv run uvicorn
PYTEST  := uv run pytest
RUFF    := uv run ruff
PYRIGHT := uv run pyright
ALEMBIC := uv run alembic

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

.PHONY: help dev test lint format migrate migration seed seed-simulate vat-update sdk-build docker-build deploy

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev: ## Start all services via docker-compose with hot-reload
	docker compose up --build

test: ## Run the test suite with coverage
	$(PYTEST) tests/ -x --tb=short --cov=src/rupiv --cov-report=term-missing

lint: ## Run linters (ruff + pyright)
	$(RUFF) check src/ tests/
	$(RUFF) format --check src/ tests/
	$(PYRIGHT)

format: ## Auto-format code with ruff
	$(RUFF) format src/ tests/
	$(RUFF) check --fix src/ tests/

migrate: ## Apply all pending database migrations
	$(ALEMBIC) upgrade head

migration: ## Create a new migration (usage: make migration msg="add users table")
	$(ALEMBIC) revision --autogenerate -m "$(msg)"

seed: ## Seed the database with sample data
	$(PYTHON) -m rupiv.seed

seed-simulate: ## Seed data + run a pricing simulation demo
	$(PYTHON) -m rupiv.seed
	$(PYTHON) -c "from rupiv.pricing_studio.templates import get_templates; print(f'Loaded {len(get_templates())} templates')"

vat-update: ## Refresh EU VAT rates (placeholder)
	$(PYTHON) -c "from rupiv.tax.rates import EU_VAT_RATES; print(f'EU VAT rates loaded: {len(EU_VAT_RATES)} countries')"

sdk-build: ## Build the client SDK package
	cd sdk && npm run build

docker-build: ## Build the Docker image
	docker build -t rupiv-api:latest .

deploy: ## Deploy via Render (push to main triggers deploy)
	git push origin main
