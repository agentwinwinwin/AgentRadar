PYTHON_BOOTSTRAP ?= python3.12
PYTHON ?= $(CURDIR)/.venv/bin/python
NPM ?= npm

.PHONY: install test lint backend-test backend-check frontend-test frontend-build compose-smoke

install: .venv/bin/python
	$(PYTHON) -m pip install -r backend/requirements/dev.txt
	cd frontend && $(NPM) install

.venv/bin/python:
	$(PYTHON_BOOTSTRAP) -m venv .venv

test: backend-test backend-check frontend-test frontend-build

lint:
	cd backend && $(PYTHON) -m ruff check .
	cd frontend && $(NPM) run lint

backend-test:
	cd backend && $(PYTHON) -m pytest

backend-check:
	cd backend && $(PYTHON) -m ruff check .
	cd backend && $(PYTHON) manage.py check

frontend-test:
	cd frontend && $(NPM) run lint
	cd frontend && $(NPM) run type-check
	cd frontend && $(NPM) run test

frontend-build:
	cd frontend && $(NPM) run build

compose-smoke:
	docker compose config --quiet
	docker compose up --build --detach
	@for attempt in $$(seq 1 30); do \
		if curl --fail --silent http://127.0.0.1:8000/api/v1/health/ >/dev/null \
			&& curl --fail --silent http://127.0.0.1:5173/api/v1/health/ >/dev/null; then \
			break; \
		fi; \
		if [ "$$attempt" -eq 30 ]; then exit 1; fi; \
		sleep 2; \
	done
	curl --fail --silent http://127.0.0.1:8000/api/v1/health/
	curl --fail --silent http://127.0.0.1:5173/api/v1/health/
	docker compose exec -T postgres pg_isready -U agentradar -d agentradar
	docker compose exec -T redis redis-cli ping
	docker compose exec -T celery-worker celery -A config inspect ping --timeout 10
