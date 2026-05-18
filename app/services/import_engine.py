"""Generic import engine supporting multiple formats: Vyapar, Tally, CSV, and future apps."""

from datetime import date
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.core.exceptions import APIError


IMPORT_FORMATS = {
    "vyapar": {
        "name": "Vyapar",
        "extensions": [".vyb"],
        "description": "Import from Vyapar accounting software (.vyb backup file)",
        "available": True,
    },
    "tally_csv": {
        "name": "Tally (CSV)",
        "extensions": [".csv"],
        "description": "Import ledger/stock/voucher data from Tally ERP exported as CSV",
        "available": False,
    },
    "tally_xml": {
        "name": "Tally (XML)",
        "extensions": [".xml"],
        "description": "Import from Tally ERP 9 via XML export",
        "available": False,
    },
    "csv_generic": {
        "name": "Generic CSV",
        "extensions": [".csv"],
        "description": "Import invoices/parties/items from a CSV file",
        "available": False,
    },
}


def list_import_formats() -> list[dict]:
    """Return list of available import formats."""
    return [
        {"id": fid, **fmt}
        for fid, fmt in IMPORT_FORMATS.items()
    ]


def import_data(tenant_id: str, user_id: str, file_path: str, import_format: str, db: Session) -> dict:
    """Route import to the correct handler."""
    if import_format == "vyapar":
        from app.services.vyapar_importer import import_vyapar_data
        return import_vyapar_data(tenant_id, user_id, file_path, db)

    raise APIError('UNSUPPORTED_FORMAT', f'Import format "{import_format}" is not yet implemented', status_code=400)


def dry_run(tenant_id: str, file_path: str, import_format: str, db: Session) -> dict:
    """Preview what an import would produce without writing."""
    if import_format == "vyapar":
        import zipfile
        import sqlite3
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(file_path, 'r') as zf:
                zf.extractall(tmpdir)

            db_file = None
            for root, _, files in os.walk(tmpdir):
                for f in files:
                    p = os.path.join(root, f)
                    try:
                        with open(p, 'rb') as fh:
                            if fh.read(6) == b'SQLite':
                                db_file = p
                                break
                    except:
                        pass

            if not db_file:
                raise APIError('INVALID_FILE', 'No SQLite DB found in Vyapar backup')

            conn = sqlite3.connect(db_file)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            stats = {}
            for table, label in [("kb_transactions WHERE txn_type IN (1,27)", "invoices"),
                                  ("kb_lineitems", "line_items"),
                                  ("kb_names WHERE name_type IN (1,2)", "parties"),
                                  ("kb_items", "items"),
                                  ("txn_payment_mapping", "payments")]:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                stats[label] = cur.fetchone()[0]

            # Transaction type breakdown
            cur.execute("SELECT txn_type, COUNT(*), SUM(txn_balance_amount) FROM kb_transactions GROUP BY txn_type")
            breakdown = [{'txn_type': r['txn_type'], 'count': r['COUNT(*)'], 'total': r['SUM(txn_balance_amount)']}
                         for r in cur.fetchall()]
            conn.close()

        return {
            'stats': stats,
            'type_breakdown': breakdown,
            'format': 'vyapar',
        }

    raise APIError('UNSUPPORTED_FORMAT', f'Dry run not available for "{import_format}"', status_code=400)
