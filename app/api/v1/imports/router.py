"""Import API endpoints supporting CSV/Excel templates.

Data types: Items, Customers, Suppliers, Sales Invoices, Purchase Bills, Payments
"""

import os
import tempfile
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.api.v1.deps import current_tenant
from app.core.database import get_db
from app.core.exceptions import ok, APIError
from app.services.import_engine import list_import_formats, get_template_csv, import_csv

router = APIRouter(prefix='/import', tags=['Import'])


@router.get('/formats')
def get_import_formats():
    """List all available import templates."""
    return ok({'formats': list_import_formats()})


@router.get('/template/{template_id}')
def download_template(template_id: str):
    """Download a CSV template file for the given data type."""
    try:
        csv_content = get_template_csv(template_id)
    except APIError as e:
        raise e

    return Response(
        content=csv_content,
        media_type='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename="{template_id}_template.csv"',
        },
    )


@router.post('/upload')
def upload_import(
    file: UploadFile = File(...),
    template_id: str = Form(...),
    dry_run: bool = Form(False),
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
):
    """Upload a CSV file to import data.

    - template_id: items, customers, suppliers, invoices_sales, invoices_purchase, payments
    - dry_run=true: preview without importing
    """
    # Validate template
    formats = list_import_formats()
    template_ids = {f['id'] for f in formats}
    if template_id not in template_ids:
        raise APIError('INVALID_TEMPLATE', f'Unknown template: {template_id}', status_code=400)

    # Read file content
    content = file.file.read()
    if not content:
        raise APIError('EMPTY_FILE', 'Uploaded file is empty', status_code=400)

    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in ('.csv',):
        raise APIError('INVALID_FORMAT', 'Only .csv files are supported', status_code=400)

    try:
        result = import_csv(tenant_id, template_id, content, db, dry_run=dry_run)
        if dry_run:
            return ok(result, 'Preview ready')
        return ok(result, f'Imported {result.get("imported", 0)} records')
    except Exception as e:
        raise APIError('IMPORT_FAILED', str(e), status_code=500)
