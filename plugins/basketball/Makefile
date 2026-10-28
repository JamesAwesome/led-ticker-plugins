.PHONY: dev test lint format typecheck

dev:  ## Install dev deps + pre-commit hooks
	uv sync --extra dev
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push

test:  ## Run tests with coverage
	uv run pytest --cov=src --cov-report=term-missing

lint:  ## Ruff lint
	uv run ruff check src tests

format:  ## Ruff format
	uv run ruff format src tests

typecheck:  ## Pyright
	uv run pyright src
