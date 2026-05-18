"""Import API endpoints supporting Vyapar, Tally, CSV, and future formats."""

import os
import tempfile
from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.api.v1.deps import current_tenant
from app.core.database import get_db
from app.core.exceptions import ok, APIError
from app.services.import_engine import list_import_formats, import_data, dry_run

router = APIRouter(prefix='/import', tags=['Import'])


@router.get('/formats')
def get_import_formats():
    """List all available import formats and their details."""
    return ok({'formats': list_import_formats()})


@router.post('/upload')
def upload_import(
    file: UploadFile = File(...),
    import_format: str = Form(...),
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
):
    """Upload and import data from supported file formats.

    Supports: vyapar (.vyb), tally (.csv/.xml), and future formats.
    """
    # Validate format
    formats = {f['id']: f for f in list_import_formats()}
    fmt = formats.get(import_format)
    if not fmt:
        raise APIError('INVALID_FORMAT', f'Unsupported import format: {import_format}', status_code=400)

    # Validate extension
    ext = os.path.splitext(file.filename or '')[1].lower()
    if ext not in fmt['extensions']:
        raise APIError('INVALID_EXTENSION',
            f'Expected {fmt["extensions"]} file, got {ext}', status_code=400)

    if not fmt['available']:
        raise APIError('NOT_AVAILABLE',
            f'Import format "{fmt["name"]}" is not yet available', status_code=400)

    # Save to temp
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix=f'import_{import_format}_') as tmp:
        content = file.file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = import_data(tenant_id, 'import_user', tmp_path, import_format, db)
        return ok(result, f'{fmt["name"]} import completed')
    except Exception as e:
        raise APIError('IMPORT_FAILED', str(e), status_code=500)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post('/dry-run')
def dry_run_import(
    file: UploadFile = File(...),
    import_format: str = Form(...),
    tenant_id: str = Depends(current_tenant),
):
    """Preview what an import would produce without writing to the database."""
    formats = {f['id']: f for f in list_import_formats()}
    fmt = formats.get(import_format)
    if not fmt:
        raise APIError('INVALID_FORMAT', f'Unsupported format: {import_format}', status_code=400)

    ext = os.path.splitext(file.filename or '')[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext, prefix=f'dry_{import_format}_') as tmp:
        content = file.file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = dry_run(tenant_id, tmp_path, import_format, db=None)
        return ok(result, 'Dry run analysis complete')
    except Exception as e:
        raise APIError('DRY_RUN_FAILED', str(e), status_code=500)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
