"""
Vyapar (.vyb) Import Service
Handles import of Vyapar backup SQLite files into the GST accounting engine.
"""
import sqlite3
import os
import uuid
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from sqlalchemy.orm import Session
from app.core.database import engine
from app.core.exceptions import APIError
from app.services.normalized_repository import normalized_repo
from app.services.gst_engine import calculate_tax


def extract_vyapar_db(vyb_path: str) -> str:
    """Extract ZIP-wrapped .vyb file to get the SQLite DB path."""
    import zipfile

    if not vyb_path.lower().endswith('.vyb'):
        raise APIError('INVALID_FILE', 'File must be .vyb (Vyapar backup)',
                       status_code=400)

    extract_dir = os.path.join(os.path.dirname(vyb_path), 'vyapar_extract')
    os.makedirs(extract_dir, exist_ok=True)

    with zipfile.ZipFile(vyb_path, 'r') as zf:
        for info in zf.infolist():
            zf.extract(info, extract_dir)

    # Find the SQLite database inside
    for root, dirs, files in os.walk(extract_dir):
        for f in files:
            full = os.path.join(root, f)
            try:
                with open(full, 'rb') as fh:
                    if fh.read(6) == b'SQLite':
                        return full
            except:
                continue

    raise APIError('INVALID_FILE', 'Could not find SQLite database in Vyapar backup')


class VyaparImporter:
    """
    Maps Vyapar schema to our GST accounting engine schema.
    """

    TXN_TYPE_MAP = {
        1: 'sales',    # Sales invoice
        27: 'purchase',  # Purchase invoice
        28: 'payment',   # Payment / Receipt
    }

    TAX_TYPE_MAP = {
        0: 'igst',
        1: 'sgst',
        2: 'cgst',
    }

    def __init__(self, tenant_id: str, user_id: str):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.vyapar_db = None
        self.stats = {
            'parties_imported': 0,
            'items_imported': 0,
            'invoices_imported': 0,
            'payments_imported': 0,
            'errors': [],
        }

    def import_from_file(self, vyb_path: str, db: Session) -> dict:
        """Main entry point: extract and import all data."""
        self.vyapar_db = extract_vyapar_db(vyb_path)
        vy_cursor = self._get_cursor()

        try:
            self._import_settings(vy_cursor, db)
            self._import_parties(vy_cursor, db)
            self._import_items(vy_cursor, db)
            self._import_invoices(vy_cursor, db)
            self._import_payments(vy_cursor, db)
        except Exception as e:
            self.stats['errors'].append(str(e))
            raise
        finally:
            # Clean up extracted files
            self._cleanup()

        return self.stats

    def _get_cursor(self) -> Any:
        """Get a SQLite cursor for the Vyapar database."""
        conn = sqlite3.connect(self.vyapar_db)
        conn.row_factory = sqlite3.Row
        return conn.cursor()

    def _cleanup(self):
        """Remove extracted temporary files."""
        import shutil
        extract_dir = os.path.dirname(self.vyapar_db)
        try:
            shutil.rmtree(extract_dir, ignore_errors=True)
        except:
            pass

    # ─── 1. IMPORT SETTINGS ──────────────────────────────────
    def _import_settings(self, cursor: Any, db: Session):
        """Import company/business settings from kb_settings."""
        cursor.execute("SELECT setting_key, setting_value FROM kb_settings")
        settings = {row['setting_key']: row['setting_value']
                     for row in cursor.fetchall()}

        company_payload = {
            'business_name': settings.get('businessName', ''),
            'legal_name': settings.get('businessLegalName', ''),
            'gstin': settings.get('gstin', ''),
            'pan': settings.get('panNumber', ''),
            'business_type': settings.get('businessType', 'Proprietorship'),
            'address_line1': settings.get('businessAddress', ''),
            'city': settings.get('businessCity', ''),
            'state': settings.get('businessState', ''),
            'pincode': settings.get('businessPincode', ''),
            'phone': settings.get('businessPhone', ''),
            'email': settings.get('businessEmail', ''),
            'financial_year_start': int(settings.get('financialYearStartMonth', 4)),
            'multiple_branches': settings.get('multipleBranches', 'false').lower() == 'true',
        }

        from app.services.settings_service import SettingsService
        svc = SettingsService()

        # Only update if we have a GSTIN (meaningful data)
        if company_payload.get('gstin'):
            try:
                svc.update_category(db, self.tenant_id, 'business', company_payload)
            except Exception as e:
                self.stats['errors'].append(f"Settings import: {e}")

    # ─── 2. IMPORT PARTIES ───────────────────────────────────
    def _import_parties(self, cursor: Any, db: Session):
        """Import parties (customers + vendors) from kb_names."""
        cursor.execute("""
            SELECT name_id, full_name, name_type, phone_number, email,
                   address, name_gstin_number, name_state, pincode,
                   party_billing_name, credit_limit, credit_limit_enabled,
                   name_customer_type
            FROM kb_names
            WHERE name_type IN (1, 2)
        """)

        for row in cursor.fetchall():
            try:
                party_type = 'Customer' if row['name_type'] == 1 else 'Supplier'
                payload = {
                    'party_id': str(uuid.uuid4()),
                    'party_name': row['full_name'] or 'Unknown',
                    'party_type': party_type,
                    'gstin': row['name_gstin_number'] or None,
                    'pan': self._extract_pan(row['name_gstin_number']) if row['name_gstin_number'] else None,
                    'state_code': self._state_name_to_code(row['name_state']),
                    'party_category': 'Regular',
                    'credit_limit': float(row['credit_limit'] or 0),
                    'credit_days': 30 if row['credit_limit_enabled'] else 0,
                    'addresses': [
                        {
                            'address_line1': row['address'] or '',
                            'city': '',
                            'state': row['name_state'] or '',
                            'pincode': row['pincode'] or '',
                            'is_primary': True,
                        }
                    ],
                }

                normalized_repo.create_party(db, self.tenant_id, payload)
                self.stats['parties_imported'] += 1
            except Exception as e:
                self.stats['errors'].append(f"Party '{row['full_name']}': {e}")

    # ─── 3. IMPORT ITEMS ─────────────────────────────────────
    def _import_items(self, cursor: Any, db: Session):
        """Import items from kb_items with tax rate mapping."""
        cursor.execute("""
            SELECT i.item_id, i.item_name, i.item_sale_unit_price,
                   i.item_purchase_unit_price, i.item_hsn_sac_code,
                   i.item_tax_id, i.item_description,
                   tc.tax_rate
            FROM kb_items i
            LEFT JOIN kb_tax_code tc ON i.item_tax_id = tc.tax_code_id
        """)

        for row in cursor.fetchall():
            try:
                rate = float(row['tax_rate'] or 0)
                payload = {
                    'item_id': str(uuid.uuid4()),
                    'item_code': f"ITEM{row['item_id']:05d}",
                    'item_name': row['item_name'] or 'Unknown Item',
                    'item_type': 'Product',
                    'hsn_code': row['item_hsn_sac_code'] or None,
                    'gst_rate': rate,
                    'selling_price': float(row['item_sale_unit_price'] or 0),
                    'purchase_price': float(row['item_purchase_unit_price'] or 0),
                }

                normalized_repo.create_item(db, self.tenant_id, payload)
                self.stats['items_imported'] += 1
            except Exception as e:
                self.stats['errors'].append(f"Item '{row['item_name']}': {e}")

    # ─── 4. IMPORT INVOICES ──────────────────────────────────
    def _import_invoices(self, cursor: Any, db: Session):
        """Import transactions as invoices with line items and tax."""
        # Only import actual invoices (type 1 = sales, 27 = purchase)
        cursor.execute("""
            SELECT DISTINCT t.txn_id, t.txn_type, t.txn_date,
                   t.txn_name_id, t.txn_balance_amount, t.txn_round_off_amount,
                   t.txn_payment_status, t.txn_tax_inclusive,
                   t.txn_place_of_supply, t.txn_reverse_charge,
                   t.txn_eway_bill_number, t.txn_irn_number,
                   t.txn_po_date, t.txn_po_ref_number,
                   t.txn_ref_number_char as ref_number,
                   n.full_name as party_name
            FROM kb_transactions t
            LEFT JOIN kb_names n ON t.txn_name_id = n.name_id
            WHERE t.txn_type IN (1, 27)
            ORDER BY t.txn_id
        """)
        transactions = cursor.fetchall()

        for txn in transactions:
            try:
                kind = self.TXN_TYPE_MAP.get(txn['txn_type'], 'sales')

                # Get line items
                cursor.execute("""
                    SELECT li.item_id, li.quantity, li.priceperunit,
                           li.total_amount, li.lineitem_tax_amount,
                           li.lineitem_tax_id, li.lineitem_discount_amount,
                           i.item_name, i.item_hsn_sac_code
                    FROM kb_lineitems li
                    LEFT JOIN kb_items i ON li.item_id = i.item_id
                    WHERE li.lineitem_txn_id = ?
                """, (txn['txn_id'],))
                lines = cursor.fetchall()

                # Get party name
                cursor.execute(
                    "SELECT full_name FROM kb_names WHERE name_id = ?",
                    (txn['txn_name_id'],))
                party_row = cursor.fetchone()
                party_name = party_row['full_name'] if party_row else 'Unknown'

                # Build line items for calculate_tax
                line_items = []
                for line in lines:
                    rate = self._get_tax_rate(cursor, line['lineitem_tax_id'])
                    line_items.append({
                        'item_name': line['item_name'] or 'Item',
                        'description': line['item_name'] or 'Item',
                        'quantity': float(line['quantity'] or 0),
                        'unit_price': float(line['priceperunit'] or 0),
                        'gst_rate': rate,
                        'hsn_code': line['item_hsn_sac_code'] or None,
                        'discount_percent': float(line['lineitem_discount_amount'] or 0),
                    })

                # Determine place of supply
                pos = str(txn['txn_place_of_supply'] or '27')
                if not pos.isdigit():
                    pos = '27'  # Default to Maharashtra if missing

                # Build payload matching import format
                payload = {
                    'invoice_date': str(txn['txn_date'] or date.today()),
                    'party_name': party_name,
                    'place_of_supply': pos,
                    'supply_type': 'B2B',
                    'invoice_type': 'Regular',
                    'reverse_charge': bool(txn['txn_reverse_charge']),
                    'notes': f"Imported from Vyapar - Txn #{txn['txn_id']}",
                    'line_items': line_items,
                    # Reference metadata
                    '_vyapar_txn_id': txn['txn_id'],
                    '_vyapar_ref': txn['ref_number'],
                    '_vyapar_party': party_name,
                }

                # Create invoice via repository
                result = normalized_repo.create_invoice(db, self.tenant_id, kind, payload)

                # If it was a paid transaction, submit it
                if txn['txn_payment_status'] == 3:  # Paid
                    try:
                        normalized_repo.submit_invoice(db, self.tenant_id, kind,
                                                        result['invoice_id'])
                    except Exception as sub_e:
                        self.stats['errors'].append(
                            f"Invoice {result['invoice_number']} submit: {sub_e}")

                self.stats['invoices_imported'] += 1
            except Exception as e:
                self.stats['errors'].append(
                    f"Invoice Txn#{txn['txn_id']} ({txn['ref_number']}): {e}")

    # ─── 5. IMPORT PAYMENTS ──────────────────────────────────
    def _import_payments(self, cursor: Any, db: Session):
        """Import payment records from payment mapping."""
        cursor.execute("""
            SELECT pm.id, pm.payment_id, pm.txn_id, pm.amount,
                   t.txn_date, t.txn_name_id, t.txn_ref_number_char,
                   pt.paymentType_type, n.full_name as party_name
            FROM txn_payment_mapping pm
            LEFT JOIN kb_transactions t ON pm.txn_id = t.txn_id
            LEFT JOIN kb_paymentTypes pt ON t.txn_payment_type_id = pt.paymentType_id
            LEFT JOIN kb_names n ON t.txn_name_id = n.name_id
            WHERE pm.amount > 0
        """)

        for row in cursor.fetchall():
            try:
                # Determine if this is a sale or purchase payment
                cursor.execute(
                    "SELECT txn_type FROM kb_transactions WHERE txn_id = ?",
                    (row['txn_id'],))
                txn = cursor.fetchone()
                payment_type = 'Receive' if txn and txn['txn_type'] == 1 else 'Make'

                mode_map = {
                    'CASH': 'Cash', 'CHEQUE': 'Cheque',
                    'BANK': 'Bank Transfer'
                }
                mode = mode_map.get(row['paymentType_type'], 'Bank Transfer')

                payload = {
                    'payment_type': payment_type,
                    'payment_mode': mode,
                    'payment_date': str(row['txn_date'] or date.today()),
                    'party_id': f"vyapar_party_{row['txn_name_id']}",
                    'amount': float(row['amount'] or 0),
                    'reference_no': row['txn_ref_number_char'] or '',
                    'narration': f"Imported from Vyapar payment #{row['payment_id']}",
                    'allocations': [],
                }

                normalized_repo.create_payment(db, self.tenant_id, payload)
                self.stats['payments_imported'] += 1
            except Exception as e:
                self.stats['errors'].append(f"Payment #{row['payment_id']}: {e}")

    # ─── HELPERS ─────────────────────────────────────────────
    def _get_tax_rate(self, cursor: Any, tax_id: int) -> float:
        """Get the tax rate percentage for a given tax code ID."""
        cursor.execute(
            "SELECT tax_rate FROM kb_tax_code WHERE tax_code_id = ?",
            (tax_id,))
        row = cursor.fetchone()
        return float(row['tax_rate'] or 0) if row else 0

    def _extract_pan(self, gstin: str) -> str | None:
        """Extract PAN from GSTIN (2nd to 13th characters)."""
        if gstin and len(gstin) >= 13:
            return gstin[2:13]
        return None

    def _state_name_to_code(self, state_name: str) -> str | None:
        """Convert state name to 2-digit code using our constants."""
        if not state_name:
            return None
        state_map = {
            'Telangana': '36', 'Andhra Pradesh': '37',
            'Maharashtra': '27', 'Karnataka': '29',
            'Tamil Nadu': '33', 'Kerala': '32',
            'Delhi': '07', 'Uttar Pradesh': '09',
            'Gujarat': '24', 'Rajasthan': '08',
            'West Bengal': '19', 'Punjab': '03',
            'Haryana': '06', 'Karnataka': '29',
        }
        # Direct code match first
        if state_name.isdigit() and len(state_name) == 2:
            return state_name
        return state_map.get(state_name)


def import_vyapar_data(tenant_id: str, user_id: str, vyb_path: str, db: Session) -> dict:
    """Public API: Import a Vyapar .vyb backup into the accounting engine."""
    importer = VyaparImporter(tenant_id=tenant_id, user_id=user_id)
    result = importer.import_from_file(vyb_path, db)

    return {
        'status': 'completed' if not result['errors'] else 'completed_with_errors',
        'stats': {
            'parties': result['parties_imported'],
            'items': result['items_imported'],
            'invoices': result['invoices_imported'],
            'payments': result['payments_imported'],
        },
        'errors': result['errors'],
    }