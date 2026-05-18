# ApexBooks GST Accounting Engine

FastAPI based multi-tenant GST accounting API with a React/Vite frontend. All clients consume `/api/v1/*`; business logic lives server-side.

## Local Backend
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .[dev]
uvicorn app.main:app --reload
```

## Local Frontend
```bash
cd gst-frontend
npm install
npm run dev
```

## Production Docker
```bash
cp .env.example .env
# Edit .env and set real secrets before starting.
docker compose up --build -d
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

## Verification

Backend:
```bash
python -m pytest tests
python -m py_compile app/core/config.py app/core/security.py app/core/rate_limit.py app/services/email_service.py app/services/otp_service.py app/services/audit_service.py app/api/v1/auth/router.py
```

Frontend:
```bash
cd gst-frontend
npm audit
npm test
npm run build
```

## Production Checklist

- Use `ENVIRONMENT=production`.
- Use PostgreSQL and Redis, not SQLite.
- Set strong `POSTGRES_PASSWORD`, MinIO credentials, and SMTP password in `.env`.
- Store JWT RSA keys under `./secrets` and keep `JWT_ALGORITHM=RS256`.
- Keep `.env` out of source control and rotate any leaked credentials.
- Configure nginx so `api.apexbooks.in` proxies to `127.0.0.1:8000`.
- Run `docker compose ps` and verify `api`, `worker`, `scheduler`, `db`, `redis`, and `minio` are healthy.
- Run the backend and frontend verification commands before release.

## Implemented Production Features

- JWT/API key authentication with token blacklist support.
- Strong password validation for registration and reset.
- OTP based password reset via SMTP email.
- OTP request rate limiting with Redis and safe in-process fallback.
- Tenant-aware API middleware with public auth and GST calculator routes.
- Parties, items, invoices, payments, accounting, GST, settings, audit logging.
- Frontend production build, dependency audit, and password validation tests.
