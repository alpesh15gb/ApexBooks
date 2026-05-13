PYTHON ?= /volume1/ApexBooks/.python/envs/gstapi/bin/python
PIP ?= /volume1/ApexBooks/.python/envs/gstapi/bin/python -m pip

.PHONY: install run test lint migrate docker-up validate smoke
install:
	$(PIP) install -e '.[dev]'
run:
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
test:
	TERM=xterm PY_COLORS=0 $(PYTHON) -m pytest -q
lint:
	$(PYTHON) -m ruff check app tests
migrate:
	$(PYTHON) -m alembic upgrade head
docker-up:
	docker compose up --build
validate:
	$(PYTHON) scripts/validate_project.py
smoke:
	$(PYTHON) scripts/manual_e2e.py
