"""
CSV/Excel Import Engine with downloadable templates.

Supports: Items, Customers, Suppliers, Invoices, Payments, GST data
Each data type has a downloadable template matching the app schema.
"""

import csv
import io
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from sqlalchemy.orm import Session
from app.core.exceptions import APIError
from app.services.normalized_repository import normalized_repo


IMPORT_TEMPLATES = {
    "items": {
        "name": "Items",
        "description": "Import products and services with HSN/SAC codes and tax rates",
        "columns": [
            {"key": "item_name", "label": "Item Name", "required": True, "example": "Laptop Dell XPS"},
            {"key": "item_code", "label": "Item Code", "required": True, "example": "SKU-001"},
            {"key": "item_type", "label": "Type (Goods/Service)", "required": False, "example": "Goods"},
            {"key": "hsn_code", "label": "HSN Code", "required": False, "example": "8471"},
            {"key": "sac_code", "label": "SAC Code", "required": False, "example": "9983"},
            {"key": "unit_of_measure", "label": "Unit", "required": False, "example": "Nos"},
            {"key": "gst_rate", "label": "GST Rate (%)", "required": False, "example": "18"},
            {"key": "selling_price", "label": "Selling Price", "required": False, "example": "50000"},
            {"key": "purchase_price", "label": "Purchase Price", "required": False, "example": "45000"},
        ],
    },
    "customers": {
        "name": "Customers",
        "description": "Import customer records with GSTIN, address, and contact details",
        "columns": [
            {"key": "party_name", "label": "Customer Name", "required": True, "example": "Acme Corp"},
            {"key": "gstin", "label": "GSTIN", "required": False, "example": "27AAAAA0000A1Z5"},
            {"key": "pan", "label": "PAN", "required": False, "example": "AAAAA0000A"},
            {"key": "state_code", "label": "State Code", "required": False, "example": "27"},
            {"key": "phone", "label": "Phone", "required": False, "example": "9876543210"},
            {"key": "email", "label": "Email", "required": False, "example": "contact@acme.com"},
            {"key": "address_line1", "label": "Address", "required": False, "example": "123 Main St"},
            {"key": "city", "label": "City", "required": False, "example": "Mumbai"},
            {"key": "pincode", "label": "Pincode", "required": False, "example": "400001"},
            {"key": "credit_limit", "label": "Credit Limit", "required": False, "example": "100000"},
            {"key": "credit_days", "label": "Credit Days", "required": False, "example": "30"},
        ],
    },
    "suppliers": {
        "name": "Suppliers",
        "description": "Import vendor/supplier records with GSTIN and contact details",
        "columns": [
            {"key": "party_name", "label": "Supplier Name", "required": True, "example": "Vendor Supplies"},
            {"key": "gstin", "label": "GSTIN", "required": False, "example": "29BBBBB0000B1Z5"},
            {"key": "pan", "label": "PAN", "required": False, "example": "BBBBB0000B"},
            {"key": "state_code", "label": "State Code", "required": False, "example": "29"},
            {"key": "phone", "label": "Phone", "required": False, "example": "9876543210"},
            {"key": "email", "label": "Email", "required": False, "example": "vendor@supplies.com"},
            {"key": "address_line1", "label": "Address", "required": False, "example": "456 Oak Rd"},
            {"key": "city", "label": "City", "required": False, "example": "Bangalore"},
            {"key": "pincode", "label": "Pincode", "required": False, "example": "560001"},
        ],
    },
    "invoices_sales": {
        "name": "Sales Invoices",
        "description": "Import sales invoices with line items",
        "columns": [
            {"key": "invoice_number", "label": "Invoice Number", "required": True, "example": "INV-001"},
            {"key": "invoice_date", "label": "Invoice Date (YYYY-MM-DD)", "required": True, "example": "2026-04-01"},
            {"key": "due_date", "label": "Due Date (YYYY-MM-DD)", "required": False, "example": "2026-05-01"},
            {"key": "party_name", "label": "Customer Name", "required": True, "example": "Acme Corp"},
            {"key": "party_gstin", "label": "Customer GSTIN", "required": False, "example": "27AAAAA0000A1Z5"},
            {"key": "place_of_supply", "label": "Place of Supply (State Code)", "required": False, "example": "27"},
            {"key": "supply_type", "label": "Supply Type", "required": False, "example": "B2B"},
            {"key": "item_name", "label": "Item Name", "required": True, "example": "Laptop"},
            {"key": "quantity", "label": "Quantity", "required": True, "example": "1"},
            {"key": "unit", "label": "Unit", "required": False, "example": "Nos"},
            {"key": "unit_price", "label": "Unit Price", "required": True, "example": "50000"},
            {"key": "gst_rate", "label": "GST Rate (%)", "required": False, "example": "18"},
            {"key": "discount_percent", "label": "Discount (%)", "required": False, "example": "0"},
        ],
    },
    "invoices_purchase": {
        "name": "Purchase Bills",
        "description": "Import purchase bills with line items",
        "columns": [
            {"key": "invoice_number", "label": "Bill Number", "required": True, "example": "PUR-001"},
            {"key": "invoice_date", "label": "Bill Date (YYYY-MM-DD)", "required": True, "example": "2026-04-01"},
            {"key": "due_date", "label": "Due Date (YYYY-MM-DD)", "required": False, "example": "2026-05-01"},
            {"key": "party_name", "label": "Supplier Name", "required": True, "example": "Vendor Supplies"},
            {"key": "party_gstin", "label": "Supplier GSTIN", "required": False, "example": "29BBBBB0000B1Z5"},
            {"key": "place_of_supply", "label": "Place of Supply (State Code)", "required": False, "example": "29"},
            {"key": "item_name", "label": "Item Name", "required": True, "example": "Raw Material"},
            {"key": "quantity", "label": "Quantity", "required": True, "example": "100"},
            {"key": "unit", "label": "Unit", "required": False, "example": "Kg"},
            {"key": "unit_price", "label": "Unit Price", "required": True, "example": "500"},
            {"key": "gst_rate", "label": "GST Rate (%)", "required": False, "example": "18"},
            {"key": "discount_percent", "label": "Discount (%)", "required": False, "example": "0"},
        ],
    },
    "payments": {
        "name": "Payments",
        "description": "Import payment records received or made",
        "columns": [
            {"key": "payment_type", "label": "Type (Receive/Pay)", "required": True, "example": "Receive"},
            {"key": "payment_date", "label": "Date (YYYY-MM-DD)", "required": True, "example": "2026-04-15"},
            {"key": "party_name", "label": "Party Name", "required": True, "example": "Acme Corp"},
            {"key": "amount", "label": "Amount", "required": True, "example": "50000"},
            {"key": "payment_mode", "label": "Mode (Cash/Bank/Cheque/UPI)", "required": False, "example": "Bank Transfer"},
            {"key": "reference_no", "label": "Reference No", "required": False, "example": "CHQ-001"},
            {"key": "narration", "label": "Narration", "required": False, "example": "Payment for INV-001"},
        ],
    },
}


class CSVImportEngine:
    """Handles CSV/Excel import with template-based column mapping."""

    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.stats = {"imported": 0, "errors": []}

    def generate_template_csv(self, template_id: str) -> str:
        """Generate a CSV template for download."""
        template = IMPORT_TEMPLATES.get(template_id)
        if not template:
            raise APIError("INVALID_TEMPLATE", f"Unknown template: {template_id}", status_code=400)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([col["label"] for col in template["columns"]])
        writer.writerow([col["example"] for col in template["columns"]])
        return output.getvalue()

    def get_template_headers(self, template_id: str) -> list[str]:
        """Get header names for column matching."""
        template = IMPORT_TEMPLATES.get(template_id)
        if not template:
            raise APIError("INVALID_TEMPLATE", f"Unknown template: {template_id}", status_code=400)
        return [col["label"] for col in template["columns"]]

    def import_csv(self, template_id: str, file_content: bytes, dry_run: bool = False) -> dict:
        """Import data from CSV content."""
        # Rollback any failed session state from previous operations
        try:
            self.db.rollback()
        except Exception:
            pass

        template = IMPORT_TEMPLATES.get(template_id)
        if not template:
            raise APIError("INVALID_TEMPLATE", f"Unknown template: {template_id}", status_code=400)

        # Parse CSV
        content = file_content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))

        if not reader.fieldnames:
            raise APIError("EMPTY_CSV", "CSV file is empty or has no headers", status_code=400)

        # Map labels to keys
        label_to_key = {col["label"]: col["key"] for col in template["columns"]}
        rows = []
        for row_num, row in enumerate(reader, start=1):
            mapped = {}
            for label, value in row.items():
                key = label_to_key.get(label.strip())
                if key:
                    mapped[key] = value.strip() if value else ""
            rows.append((row_num, mapped))

        if not rows:
            raise APIError("NO_DATA", "No data rows found in CSV", status_code=400)

        if dry_run:
            return self._preview(rows, template, template_id)

        return self._execute(rows, template, template_id)

    def _preview(self, rows: list, template: dict, template_id: str) -> dict:
        """Preview what will be imported."""
        preview_rows = []
        for row_num, row in rows[:10]:  # Preview first 10 rows
            preview_rows.append({
                "row": row_num,
                "data": {k: v for k, v in row.items() if v},
                "warnings": self._validate_row(row, template),
            })

        return {
            "template": template_id,
            "template_name": template["name"],
            "total_rows": len(rows),
            "columns": template["columns"],
            "preview": preview_rows,
            "sample_size": min(len(rows), 10),
        }

    def _execute(self, rows: list, template: dict, template_id: str) -> dict:
        """Execute the import."""
        import_method = getattr(self, f"_import_{template_id.replace('invoices_', 'invoice_')}", None)
        if not import_method:
            raise APIError("NOT_IMPLEMENTED", f"Import handler for {template_id} not implemented", status_code=500)

        for row_num, row in rows:
            try:
                import_method(row, row_num)
            except Exception as e:
                self.stats["errors"].append(f"Row {row_num}: {str(e)[:200]}")
                try:
                    self.db.rollback()
                except Exception:
                    pass

        return self.stats

    def _validate_row(self, row: dict, template: dict) -> list[str]:
        """Validate a single row against template requirements."""
        warnings = []
        for col in template["columns"]:
            if col["required"] and not row.get(col["key"], "").strip():
                warnings.append(f"Missing required field: {col['label']}")
        return warnings

    # ─── Import Handlers ──────────────────────────────────────────

    def _import_items(self, row: dict, row_num: int):
        item_code = row.get("item_code", "").strip()
        if not item_code:
            item_code = f"IMP-{uuid.uuid4().hex[:6].upper()}"
        # Check for duplicate code and append suffix if needed
        from app.models.accounting import ItemModel
        existing = self.db.query(ItemModel).filter_by(
            tenant_id=self.tenant_id, item_code=item_code, is_deleted=False
        ).first()
        if existing:
            item_code = f"{item_code}-{uuid.uuid4().hex[:3].upper()}"

        payload = {
            "item_name": row.get("item_name", ""),
            "item_code": item_code,
            "item_type": row.get("item_type", "Goods"),
            "item_type": row.get("item_type", "Goods"),
            "hsn_code": row.get("hsn_code") or None,
            "sac_code": row.get("sac_code") or None,
            "unit_of_measure": row.get("unit_of_measure", "Nos"),
            "gst_rate": float(row.get("gst_rate", 0) or 0),
            "selling_price": float(row.get("selling_price", 0) or 0),
            "purchase_price": float(row.get("purchase_price", 0) or 0),
        }
        normalized_repo.create_item(self.db, self.tenant_id, payload)
        self.stats["imported"] += 1

    def _import_customers(self, row: dict, row_num: int):
        payload = {
            "party_name": row.get("party_name", ""),
            "party_type": "Customer",
            "gstin": row.get("gstin") or None,
            "pan": row.get("pan") or None,
            "state_code": row.get("state_code") or None,
            "phone": row.get("phone") or None,
            "email": row.get("email") or None,
            "credit_limit": float(row.get("credit_limit", 0) or 0),
            "credit_days": int(row.get("credit_days", 0) or 0),
            "addresses": [{
                "line1": row.get("address_line1", ""),
                "city": row.get("city", ""),
                "pincode": row.get("pincode", ""),
                "state_code": row.get("state_code", ""),
            }] if row.get("address_line1") else [],
        }
        normalized_repo.create_party(self.db, self.tenant_id, payload)
        self.stats["imported"] += 1

    def _import_suppliers(self, row: dict, row_num: int):
        payload = {
            "party_name": row.get("party_name", ""),
            "party_type": "Vendor",
            "gstin": row.get("gstin") or None,
            "pan": row.get("pan") or None,
            "state_code": row.get("state_code") or None,
            "phone": row.get("phone") or None,
            "email": row.get("email") or None,
            "addresses": [{
                "line1": row.get("address_line1", ""),
                "city": row.get("city", ""),
                "pincode": row.get("pincode", ""),
                "state_code": row.get("state_code", ""),
            }] if row.get("address_line1") else [],
        }
        normalized_repo.create_party(self.db, self.tenant_id, payload)
        self.stats["imported"] += 1

    def _import_invoice_sales(self, row: dict, row_num: int):
        self._import_invoice(row, "sales")

    def _import_invoice_purchase(self, row: dict, row_num: int):
        self._import_invoice(row, "purchase")

    def _import_invoice(self, row: dict, kind: str):
        payload = {
            "invoice_number": row.get("invoice_number") or None,
            "invoice_date": row.get("invoice_date", str(date.today())),
            "due_date": row.get("due_date") or None,
            "party_name": row.get("party_name", ""),
            "party_gstin": row.get("party_gstin") or None,
            "place_of_supply": row.get("place_of_supply", "27"),
            "supply_type": row.get("supply_type", "B2B"),
            "line_items": [{
                "item_name": row.get("item_name", "Item"),
                "quantity": float(row.get("quantity", 1) or 1),
                "unit": row.get("unit", "Nos"),
                "unit_price": float(row.get("unit_price", 0) or 0),
                "gst_rate": float(row.get("gst_rate", 0) or 0),
                "discount_percent": float(row.get("discount_percent", 0) or 0),
            }],
        }
        normalized_repo.create_invoice(self.db, self.tenant_id, kind, payload)
        self.stats["imported"] += 1

    def _import_payments(self, row: dict, row_num: int):
        payload = {
            "payment_type": row.get("payment_type", "Receive"),
            "payment_date": row.get("payment_date", str(date.today())),
            "party_name": row.get("party_name", ""),
            "amount": float(row.get("amount", 0) or 0),
            "payment_mode": row.get("payment_mode", "Bank Transfer"),
            "reference_no": row.get("reference_no") or None,
            "narration": row.get("narration") or None,
        }
        normalized_repo.create_payment(self.db, self.tenant_id, payload)
        self.stats["imported"] += 1
