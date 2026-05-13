# GST API Engine Architecture

- API is the only source of truth. Frontends use `/api/v1/*` only.
- Tenant isolation target is PostgreSQL schema-per-company. Current scaffold exposes `X-Tenant-ID` and repository abstraction so SQLAlchemy tenant repositories can replace the in-memory repository.
- Routers are separated by modules: auth, parties, items, invoices, payments, GST, accounts, bank, TDS, inventory, settings, automations, webhooks, admin.
- GST logic lives in `app/services/gst_engine.py`, GSTR in `gstr_service.py`, e-invoice adapter in `einvoice_service.py`.
- External integrations are adapter placeholders under `app/integrations` and must be wired to approved GSP/IRP credentials.
