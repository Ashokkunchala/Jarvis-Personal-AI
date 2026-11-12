.PHONY: help install dev run test lint typecheck format migrate upgrade clean

help:
	@echo "JARVIS Personal AI - Makefile commands"
	@echo "  make install   - Install dependencies"
	@echo "  make dev       - Install dev dependencies"
	@echo "  make run       - Run enhanced server"
	@echo "  make test      - Run tests"
	@echo "  make lint      - Run Ruff (gate)"
	@echo "  make typecheck - Run mypy (informational; known baseline)"
	@echo "  make format    - Format code"
	@echo "  make migrate   - Create an empty manual migration"
	@echo "  make upgrade   - Apply migrations"
	@echo "  make clean     - Clean cache files"

install:
	pip install -r requirements.txt

dev:
	pip install -r requirements-dev.txt
	pip install -e ".[dev]"

run:
	uvicorn app.main_enhanced:app --reload --host 127.0.0.1 --port 8000

test:
	pytest -v

lint:
	ruff check .

# The project uses a hand-written sqlite3 schema, so there is no SQLAlchemy
# metadata to compare against. mypy has a pre-existing baseline of errors and
# is not a merge gate yet; use it to check the files you touch.
typecheck:
	mypy app/ --ignore-missing-imports

format:
	ruff format .

# Alembic autogenerate cannot work with target_metadata = None. Add the SQL to
# the generated file by hand and review it before running `make upgrade`.
migrate:
	alembic revision -m "jarvis schema change"

upgrade:
	alembic upgrade head

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache
