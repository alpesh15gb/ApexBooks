"""Import engine supporting CSV/Excel templates: Items, Customers, Suppliers, Invoices, Payments."""

from typing import Optional
from sqlalchemy.orm import Session
from app.core.exceptions import APIError
from app.services.csv_importer import CSVImportEngine, IMPORT_TEMPLATES


def list_import_formats() -> list[dict]:
    """Return list of available import templates."""
    return [
        {
            "id": tid,
            "name": tpl["name"],
            "description": tpl["description"],
            "available": True,
            "extensions": [".csv"],
        }
        for tid, tpl in IMPORT_TEMPLATES.items()
    ]


def get_template_csv(template_id: str) -> str:
    """Generate a downloadable CSV template."""
    from app.services.csv_importer import CSVImportEngine

    engine = CSVImportEngine(None, None)  # No DB needed for template generation
    return engine.generate_template_csv(template_id)


def import_csv(tenant_id: str, template_id: str, file_content: bytes, db: Session, dry_run: bool = False) -> dict:
    """Import CSV data for a given template type."""
    engine = CSVImportEngine(db, tenant_id)
    return engine.import_csv(template_id, file_content, dry_run=dry_run)
