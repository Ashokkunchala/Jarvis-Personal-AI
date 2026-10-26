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
	alembic revision --autogenerate -m "Send a message to a user.  MSG {username | sessionname | sessionid | @filename | *}     [/SERVER:servername] [/TIME:seconds] [/V] [/W] [message]    username            Identifies the specified username.   sessionname         The name of the session.   sessionid           The ID of the session.   @filename           Identifies a file containing a list of usernames,                       sessionnames, and sessionids to send the message to.   *                   Send message to all sessions on specified server.   /SERVER:servername  server to contact (default is current).   /TIME:seconds       Time delay to wait for receiver to acknowledge msg.   /V                  Display information about actions being performed.   /W                  Wait for response from user, useful with /V.   message             Message to send.  If none specified, prompts for it                       or reads from stdin. "

upgrade:
	alembic upgrade head

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache
