from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.api.v1.deps import current_tenant
from app.core.database import get_db
from app.core.exceptions import ok, APIError
from app.services.vyapar_importer import import_vyapar_data
import tempfile
import os

router = APIRouter(prefix='/import', tags=['Import'])


@router.post('/vyapar')
def import_vyapar(
    file: UploadFile = File(...),
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
):
    """Import a Vyapar .vyb backup file into the accounting engine."""
    # Validate file type
    if not file.filename.endswith('.vyb'):
        raise APIError('INVALID_FILE',
                        'Only .vyb (Vyapar backup) files are accepted',
                        status_code=400)

    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(
        delete=False, suffix='.vyb', prefix='vyapar_'
    ) as tmp:
        content = file.file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = import_vyapar_data(tenant_id, 'import_user', tmp_path, db)

        return ok(result, 'Vyapar import completed')
    except Exception as e:
        raise APIError('IMPORT_FAILED', str(e), status_code=500)
    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post('/dry-run')
def import_vyapar_dry_run(
    file: UploadFile = File(...),
    tenant_id: str = Depends(current_tenant),
):
    """Preview what a Vyapar import would produce (no DB writes)."""
    if not file.filename.endswith('.vyb'):
        raise APIError('INVALID_FILE',
                        'Only .vyb files accepted', status_code=400)

    import zipfile
    import sqlite3

    # Extract to temp
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(file.file, 'r') as zf:
            zf.extractall(tmpdir)

        # Find SQLite file
        db_file = None
        for root, _, files in os.walk(tmpdir):
            for f in files:
                path = os.path.join(root, f)
                try:
                    with open(path, 'rb') as fh:
                        if fh.read(6) == b'SQLite':
                            db_file = path
                            break
                except:
                    pass

        if not db_file:
            raise APIError('INVALID_FILE', 'No SQLite DB in Vyapar backup')

        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Count data
        cursor.execute("SELECT COUNT(*) FROM kb_transactions WHERE txn_type IN (1, 27)")
        inv_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM kb_lineitems")
        line_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM kb_names WHERE name_type IN (1, 2)")
        party_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM kb_items")
        item_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM txn_payment_mapping")
        pmt_count = cursor.fetchone()[0]

        # Transaction type breakdown
        cursor.execute("""
            SELECT txn_type, COUNT(*), SUM(txn_balance_amount)
            FROM kb_transactions
            GROUP BY txn_type
        """)
        type_breakdown = [
            {'txn_type': r['txn_type'], 'count': r['COUNT(*)'],
             'total': r['SUM(txn_balance_amount)']}
            for r in cursor.fetchall()
        ]

        conn.close()

        return ok({
            'source_file': file.filename,
            'stats': {
                'invoices': inv_count,
                'line_items': line_count,
                'parties': party_count,
                'items': item_count,
                'payments': pmt_count,
            },
            'type_breakdown': type_breakdown,
        }, 'Dry run analysis')