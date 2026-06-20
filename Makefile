.PHONY: dev test lint format format-check

dev:
	uv sync --extra dev

test:
	uv run pytest plugins $(foreach m,$(wildcard plugins/*/src),--cov=$(m)) --cov-report=term-missing

lint:
	uv run ruff check plugins
	uv run pyright plugins/*/src

format:
	uv run ruff format plugins

format-check:
	uv run ruff format --check plugins
