from fastapi import APIRouter
from app.api.v1.auth.router import router as auth_router
from app.api.v1.parties.router import router as parties_router
from app.api.v1.items.router import router as items_router
from app.api.v1.items.masters import router as item_masters_router
from app.api.v1.invoices.router import router as invoices_router
from app.api.v1.payments.router import router as payments_router
from app.api.v1.gst.router import router as gst_router
from app.api.v1.accounts.router import router as accounts_router
from app.api.v1.bank.router import router as bank_router
from app.api.v1.tds.router import router as tds_router
from app.api.v1.inventory.router import router as inventory_router
from app.api.v1.settings.router import router as settings_router
from app.api.v1.automations.router import router as automations_router
from app.api.v1.webhooks.router import router as webhooks_router
from app.api.v1.admin.router import router as admin_router
from app.api.v1.imports.router import router as imports_router

router = APIRouter(prefix='/api/v1')
for r in [auth_router, parties_router, items_router, item_masters_router, invoices_router,
           payments_router, gst_router, accounts_router, bank_router, tds_router,
           inventory_router, settings_router, automations_router, webhooks_router,
           admin_router, imports_router]:
    router.include_router(r)
