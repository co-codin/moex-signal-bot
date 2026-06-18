.PHONY: help install test lint format check precommit dry-help admin-web docker-build compose-up compose-down compose-logs workers

PYTHON ?= python3
PYTHONPATH ?= src
WORKERS ?= 3
DRY_RUN_COMMAND ?= /help

help:
	@echo "Targets:"
	@echo "  install       Install package with dev dependencies"
	@echo "  test          Run pytest"
	@echo "  lint          Run Ruff lint"
	@echo "  format        Format code with Ruff"
	@echo "  check         Run tests, lint, format check, and diff whitespace check"
	@echo "  precommit     Run pre-commit on all files"
	@echo "  dry-help      Run dry-run command, default /help"
	@echo "  admin-web     Run local access-control admin web panel"
	@echo "  docker-build  Build Docker image"
	@echo "  compose-up    Start Postgres, Redis, bot, scheduler, and worker"
	@echo "  workers       Scale scanner-worker, default WORKERS=3"
	@echo "  compose-logs  Follow bot, scheduler, and worker logs"
	@echo "  compose-down  Stop Compose services"

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest -q

lint:
	ruff check .

format:
	ruff format .

check:
	$(PYTHON) -m pytest -q
	ruff check .
	ruff format --check .
	git diff --check

precommit:
	pre-commit run --all-files

dry-help:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m moex_signal_bot --dry-run "$(DRY_RUN_COMMAND)"

admin-web:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m moex_signal_bot --admin-web

docker-build:
	docker build --pull=false -t moex-signal-bot .

compose-up:
	docker compose up -d --build

workers:
	docker compose up -d --scale scanner-worker=$(WORKERS)

compose-logs:
	docker compose logs -f bot scanner-scheduler scanner-worker

compose-down:
	docker compose down
