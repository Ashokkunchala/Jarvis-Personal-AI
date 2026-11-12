.PHONY: help install dev run test lint format migrate upgrade clean docker-build docker-up

help:
	@echo "JARVIS Personal AI - Makefile commands"
	@echo "  make install   - Install dependencies"
	@echo "  make dev       - Install dev dependencies"
	@echo "  make run       - Run enhanced server"
	@echo "  make test      - Run tests"
	@echo "  make lint      - Run linting"
	@echo "  make format    - Format code"
	@echo "  make migrate   - Create migration"
	@echo "  make upgrade   - Apply migrations"
	@echo "  make docker-up - Start with docker-compose"
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
	ruff check app/ tests/
	mypy app/ --ignore-missing-imports

format:
	ruff format app/ tests/

migrate:
	alembic revision --autogenerate -m "Initial schema"

upgrade:
	alembic upgrade head

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

# Cross-platform (the previous `find`-based recipe failed on Windows hosts).
clean:
	python -c "import pathlib, shutil; roots=[p for p in pathlib.Path('.').iterdir() if p.is_dir() and p.name not in {'.venv','venv','.git','node_modules'}]; [shutil.rmtree(d, ignore_errors=True) for r in roots for d in r.rglob('__pycache__')]; [f.unlink() for r in roots for f in r.rglob('*.pyc')]; [shutil.rmtree(c, ignore_errors=True) for c in map(pathlib.Path, ('.pytest_cache','.mypy_cache','.ruff_cache'))]"
