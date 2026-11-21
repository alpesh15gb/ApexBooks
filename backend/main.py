import book_services as services
import os
from accounting import db
from build_info import BUILD_REVISION
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, backups, banking, companies as company_routes, documents, gst, inventory, masters, ocr, reports
from sqlalchemy import select
from sqlalchemy.orm import Session


app = FastAPI(title='Apex Books API', version='1.5.0', docs_url='/api/docs', redoc_url='/api/redoc', openapi_url='/api/openapi.json')


app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(','), allow_methods=['*'], allow_headers=['*'])


@app.get('/api/health')
def health(session: Session = Depends(db)):
    session.execute(select(1)).scalar_one()
    return {'status': 'ok', 'version': app.version, 'build_revision': BUILD_REVISION}


@app.get('/api/ready')
def ready(session: Session = Depends(db)):
    return {'status': 'ready', 'version': app.version, 'build_revision': BUILD_REVISION}


app.include_router(ocr.router)
app.include_router(auth.router)
app.include_router(company_routes.router)
app.include_router(documents.router)
app.include_router(masters.router)
app.include_router(inventory.router)
app.include_router(banking.router)
app.include_router(reports.router)
app.include_router(gst.router)
app.include_router(backups.router)

from workflow_extensions import install as install_workflows
install_workflows(app, services)

from pos_register import install as install_pos_register
install_pos_register(app, services)

from pos_returns import install as install_pos_returns
install_pos_returns(app, services)

from purchase_receiving import install as install_purchase_receiving
install_purchase_receiving(app, services)

from inventory_setup import install as install_inventory_setup
install_inventory_setup(app, services)

from company_restore import install as install_company_restore
install_company_restore(app, services)

from auth_workflows import install as install_auth_workflows
install_auth_workflows(app, services)

from document_edits import install as install_document_edits
install_document_edits(app, services)

from cancellation import install as install_cancellation
install_cancellation(app, services)

from receipt_corrections import install as install_receipt_corrections
install_receipt_corrections(app, services)

from pay_at_invoice import install as install_pay_at_invoice
install_pay_at_invoice(app, services)

from statements import install as install_statements
install_statements(app, services)

from gst_returns import install as install_gst_returns
install_gst_returns(app, services)

from party_statements import install as install_party_statements
install_party_statements(app, services)
from day_book import install as install_day_book
install_day_book(app, services)

from commerce import install as install_commerce
install_commerce(app, services)

from everyday_features import install as install_everyday_features
install_everyday_features(app, services)

from recurring_drafts import install as install_recurring_drafts
install_recurring_drafts(app, services)

from api_capabilities import install as install_api_capabilities
install_api_capabilities(app, services)

from document_attachments import install as install_document_attachments
install_document_attachments(app, services)

from backup_transport import install as install_backup_transport
install_backup_transport(app, services)


def __getattr__(name):
    """Keep the module interface used by migration tools and API clients."""
    return getattr(services, name)
