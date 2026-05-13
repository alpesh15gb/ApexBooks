from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.exceptions import APIError
from app.core.config import get_settings
from app.models.e2e import CompanyRecord

def _default_settings() -> dict:
    return {
        "business": {
            "business_name": "", "legal_name": "", "gstin": "", "pan": "",
            "business_type": "Proprietorship", "address_line1": "", "city": "",
            "state": "", "pincode": "", "phone": "", "email": "", "website": "",
            "logo_url": None, "signature_url": None, "upi_qr_url": None,
            "default_currency": "INR", "financial_year_start": 4,
            "timezone": "Asia/Kolkata", "language": "en",
            "multiple_branches": False, "multiple_warehouses": False,
            "multiple_gst_registrations": False,
        },
        "invoice": {
            "sales": {
                "series": {"prefix": "INV", "starting_number": 1, "auto_numbering": True, "number_reset_yearly": True},
                "default_due_days": 0, "show_payment_qr": False, "show_bank_details": True,
                "show_hsn_sac": True, "show_item_image": False, "show_transport_details": False,
                "show_eway_details": False, "show_einvoice_irn": True, "round_off_method": "Normal",
                "allow_negative_stock": False, "auto_save_draft": True, "print_after_save": False,
            },
            "purchase": {
                "series": {"prefix": "PUR", "starting_number": 1, "auto_numbering": True, "number_reset_yearly": True},
                "vendor_bill_number_mandatory": True, "duplicate_bill_warning": True,
            },
            "template": {
                "template_style": "Modern", "font_size": "Small", "primary_color": "#10B981",
                "terms_and_conditions": "", "footer_notes": "", "show_custom_fields": False,
            },
        },
        "gst": {
            "core": {
                "enabled": True, "scheme": "regular", "inclusive_exclusive": "exclusive",
                "default_rates": {
                    "igst": 18.0, "cgst": 9.0, "sgst": 9.0, "cess": 0.0,
                    "igst_5": 5.0, "cgst_5": 2.5, "sgst_5": 2.5,
                    "igst_12": 12.0, "cgst_12": 6.0, "sgst_12": 6.0,
                    "igst_0": 0.0, "gold_rate": 3.0,
                },
                "reverse_charge": False, "tds_deducted": False, "tds_rate": 0.0, "tcs_rate": 0.0,
            },
            "einvoice": {
                "enabled": False, "gsp_provider": "", "auto_generate_irn": True,
                "auto_cancel_irn": True, "auto_pdf_attach": True,
            },
            "ewaybill": {
                "enabled": False, "default_distance_km": 0, "require_vehicle_details": True,
                "require_transporter_id": False, "auto_generation": True,
            },
            "returns": {
                "gstr1_enabled": True, "gstr3b_enabled": True, "gstr2a_reconciliation": True,
                "auto_match_gstr2a": True, "export_sez_enabled": True, "lut_bond_management": False,
            },
        },
        "accounting": {
            "ledger_defaults": {
                "default_sales_ledger": "Accounts Receivable", "default_purchase_ledger": "Accounts Payable",
                "cash_ledger": "Cash", "round_off_ledger": "Round Off",
                "freight_inward_ledger": "Freight Inward", "freight_outward_ledger": "Freight Outward",
            },
            "journal": {
                "auto_journal_posting": True, "allow_edit_locked_entries": False,
                "allow_backdated_entries": True, "require_voucher_approval": False,
            },
            "financial_controls": {
                "lock_books_till_date": None, "audit_mode": False,
                "freeze_transactions_before": None, "voucher_approval_workflow": False,
            },
            "profit_and_loss": {
                "cost_center_enabled": False, "branch_accounting": False,
                "department_accounting": False,
            },
        },
        "inventory": {
            "controls": {
                "allow_negative_stock": False, "batch_tracking": False, "expiry_tracking": False,
                "serial_number_tracking": False, "barcode_enabled": False, "auto_sku_generation": True,
            },
            "pricing": {
                "enable_wholesale": False, "enable_retail": False,
                "enable_dealer": False, "enable_custom_pricing": False,
            },
            "valuation": {"method": "fifo"},
            "multi_warehouse": False, "stock_transfer_enabled": False,
        },
        "payments": {
            "upi": {"enabled": False, "qr_codes": []},
            "gateways": {"razorpay": False, "phonepe": False, "cashfree": False, "stripe": False},
            "banking": {"bank_accounts": [], "auto_reconciliation": False, "import_bank_statements": False},
            "reminders": {
                "whatsapp_enabled": False, "sms_enabled": False, "email_enabled": True,
                "days_before_due": 3, "days_after_due": 7,
            },
        },
        "roles": {
            "roles": [
                {
                    "name": "Admin", "description": "Full access",
                    "permissions": {
                        "view_all_data": True, "edit_all_data": True, "delete_entries": True,
                        "approve_vouchers": True, "discount_override": True, "report_access": True,
                        "stock_adjustment": True, "export_data": True, "import_data": True,
                        "settings_access": True, "financial_reports": True, "gst_reports": True,
                    },
                },
                {
                    "name": "Accountant", "description": "Accounting & reports",
                    "permissions": {
                        "view_all_data": True, "edit_all_data": True, "delete_entries": False,
                        "approve_vouchers": True, "discount_override": False, "report_access": True,
                        "stock_adjustment": False, "export_data": True, "import_data": False,
                        "settings_access": False, "financial_reports": True, "gst_reports": True,
                    },
                },
                {
                    "name": "Salesman", "description": "Sales entry only",
                    "permissions": {
                        "view_all_data": False, "edit_all_data": False, "delete_entries": False,
                        "approve_vouchers": False, "discount_override": False, "report_access": False,
                        "stock_adjustment": False, "export_data": False, "import_data": False,
                        "settings_access": False, "financial_reports": False, "gst_reports": False,
                    },
                },
                {
                    "name": "Auditor", "description": "Read-only + audit trail",
                    "permissions": {
                        "view_all_data": True, "edit_all_data": False, "delete_entries": False,
                        "approve_vouchers": False, "discount_override": False, "report_access": True,
                        "stock_adjustment": False, "export_data": True, "import_data": False,
                        "settings_access": False, "financial_reports": True, "gst_reports": True,
                    },
                },
            ]
        },
        "notifications": {
            "whatsapp": {"enabled": False, "api_key": ""},
            "sms": {"enabled": False, "provider": "", "api_key": ""},
            "email": {
                "enabled": True, "smtp_host": "", "smtp_port": 587,
                "smtp_user": "", "smtp_password": "",
                "sender_email": "", "sender_name": "",
            },
            "events": {
                "invoice_sent": True, "payment_reminder": True, "order_update": True,
                "payment_received": True, "invoice_due": True,
                "delivery_note": False, "credit_note": True,
            },
        },
        "backup": {
            "backup": {
                "auto_backup": True, "backup_frequency": "daily",
                "google_drive": False, "onedrive": False,
                "local_backup_path": "./backups", "retention_days": 30,
            },
            "offline": {"enabled": False, "sync_on_reconnect": True},
            "sync": {"multi_device_sync": False, "local_network_sync": False},
        },
        "reports": {
            "filters": {
                "date_range": "this_month", "hide_profit_from_staff": False,
                "default_page_size": 25,
            },
            "favorites": [],
            "scheduled": {"enabled": False, "frequency": "weekly", "recipients": [], "report_types": []},
            "export_formats": ["excel", "pdf", "csv"],
        },
        "pos": {
            "thermal_printer": {
                "printer_name": "", "printer_type": "thermal",
                "paper_width": 58, "auto_cut": True,
            },
            "barcode_scanner": False,
            "customer_display": {"enabled": False, "display_type": "led"},
            "fast_billing_mode": False, "offline_pos": False,
            "default_payment_mode": "cash",
        },
        "automations": {
            "reminders": {
                "payment_reminder": True, "due_date_reminder_days": 3,
                "overdue_reminder_days": 1,
            },
            "gst": {
                "filing_alerts": True, "alert_days_before": 7,
                "auto_gstr1": False, "auto_gstr3b": False,
            },
            "recurring_invoices": {"enabled": False, "generate_days_before": 1},
            "stock_alerts": {
                "low_stock_alert": True, "low_stock_threshold": 10,
                "out_of_stock_alert": True,
            },
            "accounting": {"auto_post_gl": True, "reconcile_on_payment": True},
        },
        "security": {
            "two_factor": {"enabled": False, "method": "totp"},
            "pin_lock": {"enabled": False, "timeout_minutes": 5},
            "device_restrictions": {"enabled": False, "max_devices": 5},
            "login_history": True,
            "ip_restrictions": [],
            "sessions": {"timeout_minutes": 480, "max_concurrent_sessions": 3},
        },
        "integrations": {
            "tally": {"enabled": False, "sync_direction": "import", "last_sync": None},
            "excel_import_export": True,
            "shopify": {"enabled": False, "store_url": None, "api_key": None},
            "woocommerce": {"enabled": False, "store_url": None, "api_key": None},
            "amazon": {"enabled": False, "store_url": None, "api_key": None},
            "ondc": False,
            "webhooks": [],
        },
        "developer": {
            "api_keys": [], "webhook_endpoints": [],
            "event_logs_enabled": True, "queue_monitor_enabled": True,
            "background_jobs_enabled": True, "audit_log_retention_days": 365,
        },
    }


class SettingsService:
    """Business logic layer for tenant settings."""

    def get_settings(self, db: Session, tenant_id: str) -> dict:
        record = db.query(CompanyRecord).filter_by(company_id=tenant_id).first()
        if not record:
            raise APIError('TENANT_NOT_FOUND', f'Tenant {tenant_id} not found', status_code=404)
        settings_obj = record.payload if record.payload else {}
        if not settings_obj:
            settings_obj = _default_settings()
            record.payload = settings_obj
            db.flush()
        return settings_obj

    def get_category(self, db: Session, tenant_id: str, category: str) -> dict:
        settings = self.get_settings(db, tenant_id)
        if category not in settings:
            raise APIError('INVALID_CATEGORY', f'Unknown category: {category}', status_code=400)
        return settings[category]

    def update_category(self, db: Session, tenant_id: str, category: str, payload: dict):
        record = db.query(CompanyRecord).filter_by(company_id=tenant_id).first()
        if not record:
            raise APIError('TENANT_NOT_FOUND', f'Tenant {tenant_id} not found', status_code=404)

        default = _default_settings()
        if category not in default:
            raise APIError('INVALID_CATEGORY', f'Unknown category: {category}', status_code=400)

        if not record.payload:
            record.payload = _default_settings()

        existing = record.payload.get(category, {})
        if isinstance(existing, dict):
            existing.update(payload)
        record.updated_at = __import__('datetime').datetime.utcnow()
        db.flush()

        from app.services.audit_service import AuditLog
        audit = AuditLog(db)
        audit.log(tenant_id, 'system', 'SETTINGS_UPDATED', f'settings:{category}', None,
                  {'category': category, 'fields_changed': list(payload.keys())})

        return record.payload[category]

    def update_bulk(self, db: Session, tenant_id: str, payload: dict):
        record = db.query(CompanyRecord).filter_by(company_id=tenant_id).first()
        if not record:
            raise APIError('TENANT_NOT_FOUND', f'Tenant {tenant_id} not found', status_code=404)

        if not record.payload:
            record.payload = _default_settings()

        default = _default_settings()
        for category, data in payload.items():
            if category not in default:
                raise APIError('INVALID_CATEGORY', f'Unknown category: {category}', status_code=400)
            existing = record.payload.get(category, {})
            if isinstance(existing, dict):
                existing.update(data)

        record.updated_at = __import__('datetime').datetime.utcnow()
        db.flush()
        return record.payload

    def get_invoice_numbering(self, db: Session, tenant_id: str, kind: str) -> dict:
        settings = self.get_settings(db, tenant_id)
        inv = settings.get('invoice', {})
        if kind == 'sales':
            series = inv.get('sales', {}).get('series', {})
        elif kind == 'purchase':
            series = inv.get('purchase', {}).get('series', {})
        else:
            series = {}
        return {
            'prefix': series.get('prefix', 'INV' if kind == 'sales' else 'PUR'),
            'starting_number': series.get('starting_number', 1),
            'auto_numbering': series.get('auto_numbering', True),
            'number_reset_yearly': series.get('number_reset_yearly', True),
        }

    def is_gst_enabled(self, db: Session, tenant_id: str) -> bool:
        settings = self.get_settings(db, tenant_id)
        return settings.get('gst', {}).get('core', {}).get('enabled', True)

    def is_einvoice_enabled(self, db: Session, tenant_id: str) -> bool:
        return self.get_category(db, tenant_id, 'gst').get('einvoice', {}).get('enabled', False)

    def is_ewaybill_enabled(self, db: Session, tenant_id: str) -> bool:
        return self.get_category(db, tenant_id, 'gst').get('ewaybill', {}).get('enabled', False)


settings_service = SettingsService()