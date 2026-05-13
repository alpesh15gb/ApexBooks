# Indian GST Accounting API Engine

FastAPI based multi-tenant GST accounting API. All clients consume `/api/v1/*`; business logic lives server-side.

## Run
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

## Docker
```bash
docker compose up --build
```

Docs: http://localhost:8000/docs and `/redoc`.

## End-to-end engine status

The engine now includes persistent SQL-backed flows for:
- company registration and tenant schema creation hook
- JWT/API key authentication
- parties/items CRUD
- invoice numbering, tax calculation, invoice persistence, submit and GL posting
- payments persistence
- GST GSTR-1/GSTR-3B views from stored invoices

Run with Docker:
```bash
cp .env.example .env
docker compose up --build
```

Run tests in Python 3.11:
```bash
make install
make test
```
