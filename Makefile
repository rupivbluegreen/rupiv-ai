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

.PHONY: help dev test lint format migrate migration seed sdk-build docker-build deploy

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev: ## Start the dev server with hot-reload
	$(UVICORN) rupiv.main:app --reload --host 0.0.0.0 --port 8000

test: ## Run the test suite with coverage
	$(PYTEST) --cov=rupiv --cov-report=term-missing

lint: ## Run linters (ruff + pyright)
	$(RUFF) check .
	$(PYRIGHT)

format: ## Auto-format code with ruff
	$(RUFF) format .
	$(RUFF) check --fix .

migrate: ## Apply all pending database migrations
	$(ALEMBIC) upgrade head

migration: ## Create a new migration (usage: make migration msg="add users table")
	$(ALEMBIC) revision --autogenerate -m "$(msg)"

seed: ## Seed the database with sample data
	$(PYTHON) -m rupiv.scripts.seed

sdk-build: ## Build the client SDK package
	cd sdk && npm run build

docker-build: ## Build the Docker image
	docker build -t rupiv-api:latest .

deploy: ## Deploy via Render (push to main triggers deploy)
	git push origin main
