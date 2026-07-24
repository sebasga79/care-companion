.PHONY: install dev test lint verify

# Todos los targets son idempotentes: se pueden correr repetidas veces sin
# efectos secundarios acumulativos (REP-001/REP-003).

install:
	cd api && uv sync --all-groups

dev:
	cd api && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	cd api && uv run pytest

lint:
	cd api && uv run ruff check .

verify: lint test
	@echo "verify: lint + tests OK"
