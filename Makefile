.PHONY: dev test lint format

dev:
	uv sync --extra dev

test:
	uv run pytest plugins --cov-report=term-missing

lint:
	uv run ruff check plugins
	uv run pyright plugins/*/src

format:
	uv run ruff format plugins
