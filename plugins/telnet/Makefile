.PHONY: dev test lint format typecheck smoke-build smoke-run smoke-stop

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

smoke-build:  ## Build the headless smoke/profiling image (Dockerfile.smoke)
	docker build -f Dockerfile.smoke -t led-ticker-telnet-smoke .

smoke-run: smoke-build  ## Run the smoke container, then: telnet localhost 2300
	-docker rm -f tsmoke 2>/dev/null
	docker run -d --name tsmoke -p 2300:2300 led-ticker-telnet-smoke
	@echo "connect: telnet localhost 2300   (stop: make smoke-stop)"

smoke-stop:  ## Stop + remove the smoke container
	-docker rm -f tsmoke 2>/dev/null
