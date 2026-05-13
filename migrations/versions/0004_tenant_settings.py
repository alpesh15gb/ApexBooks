"""add tenant_settings table

Revision ID: 0004_tenant_settings
Revises: 0003_production_hardening
Create Date: 2026-05-14
"""
import json
from alembic import op
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, UniqueConstraint, Index
from datetime import datetime

revision = '0004_tenant_settings'
down_revision = '0003_production_hardening'
branch_labels = None
depends_on = None

# Full default settings for onboarding
DEFAULT_SETTINGS = {
    "business": {
        "business_name": "", "legal_name": "", "gstin": "", "pan": "",
        "business_type": "Proprietorship", "address_line1": "", "city": "",
        "state": "", "pincode": "", "phone": "", "email": "", "website": "",
        "default_currency": "INR", "financial_year_start": 4,
        "timezone": "Asia/Kolkata", "language": "en",
        "multiple_branches": False, "multiple_warehouses": False,
        "multiple_gst_registrations": False,
    },
    "invoice": {
        "sales": {"series": {"prefix": "INV", "starting_number": 1, "auto_numbering": True, "number_reset_yearly": True},
                  "default_due_days": 0, "show_payment_qr": False, "show_bank_details": True,
                  "show_hsn_sac": True, "show_item_image": False, "show_transport_details": False,
                  "show_eway_details": False, "show_einvoice_irn": True, "round_off_method": "Normal",
                  "allow_negative_stock": False, "auto_save_draft": True, "print_after_save": False},
        "purchase": {"series": {"prefix": "PUR", "starting_number": 1, "auto_numbering": True, "number_reset_yearly": True},
                     "vendor_bill_number_mandatory": True, "duplicate_bill_warning": True},
        "template": {"template_style": "Modern", "font_size": "Small", "primary_color": "#10B981",
                     "terms_and_conditions": "", "footer_notes": "", "show_custom_fields": False},
    },
    "gst": {
        "core": {"enabled": True, "scheme": "regular", "inclusive_exclusive": "exclusive",
                 "default_rates": {"igst": 18.0, "cgst": 9.0, "sgst": 9.0, "cess": 0.0,
                                   "igst_5": 5.0, "cgst_5": 2.5, "sgst_5": 2.5,
                                   "igst_12": 12.0, "cgst_12": 6.0, "sgst_12": 6.0,
                                   "igst_0": 0.0, "gold_rate": 3.0},
                 "reverse_charge": False, "tds_deducted": False, "tds_rate": 0.0, "tcs_rate": 0.0},
        "einvoice": {"enabled": False, "gsp_provider": "", "auto_generate_irn": True,
                     "auto_cancel_irn": True, "auto_pdf_attach": True},
        "ewaybill": {"enabled": False, "default_distance_km": 0, "require_vehicle_details": True,
                     "require_transporter_id": False, "auto_generation": True},
        "returns": {"gstr1_enabled": True, "gstr3b_enabled": True, "gstr2a_reconciliation": True,
                    "auto_match_gstr2a": True, "export_sez_enabled": True, "lut_bond_management": False},
    },
    "accounting": {
        "ledger_defaults": {"default_sales_ledger": "Accounts Receivable", "default_purchase_ledger": "Accounts Payable",
                            "cash_ledger": "Cash", "round_off_ledger": "Round Off",
                            "freight_inward_ledger": "Freight Inward", "freight_outward_ledger": "Freight Outward"},
        "journal": {"auto_journal_posting": True, "allow_edit_locked_entries": False,
                    "allow_backdated_entries": True, "require_voucher_approval": False},
        "financial_controls": {"lock_books_till_date": None, "audit_mode": False,
                               "freeze_transactions_before": None, "voucher_approval_workflow": False},
        "profit_and_loss": {"cost_center_enabled": False, "branch_accounting": False, "department_accounting": False},
    },
    "inventory": {
        "controls": {"allow_negative_stock": False, "batch_tracking": False, "expiry_tracking": False,
                     "serial_number_tracking": False, "barcode_enabled": False, "auto_sku_generation": True},
        "pricing": {"enable_wholesale": False, "enable_retail": False, "enable_dealer": False, "enable_custom_pricing": False},
        "valuation": {"method": "fifo"}, "multi_warehouse": False, "stock_transfer_enabled": False,
    },
    "payments": {
        "upi": {"enabled": False, "qr_codes": []},
        "gateways": {"razorpay": False, "phonepe": False, "cashfree": False, "stripe": False},
        "banking": {"bank_accounts": [], "auto_reconciliation": False, "import_bank_statements": False},
        "reminders": {"whatsapp_enabled": False, "sms_enabled": False, "email_enabled": True, "days_before_due": 3, "days_after_due": 7},
    },
    "roles": {"roles": [
        {"name": "Admin", "description": "Full access", "permissions": {"view_all_data": True, "edit_all_data": True, "delete_entries": True, "approve_vouchers": True, "discount_override": True, "report_access": True, "stock_adjustment": True, "export_data": True, "import_data": True, "settings_access": True, "financial_reports": True, "gst_reports": True}},
        {"name": "Accountant", "description": "Accounting & reports", "permissions": {"view_all_data": True, "edit_all_data": True, "delete_entries": False, "approve_vouchers": True, "discount_override": False, "report_access": True, "stock_adjustment": False, "export_data": True, "import_data": False, "settings_access": False, "financial_reports": True, "gst_reports": True}},
        {"name": "Salesman", "description": "Sales entry only", "permissions": {"view_all_data": False, "edit_all_data": False, "delete_entries": False, "approve_vouchers": False, "discount_override": False, "report_access": False, "stock_adjustment": False, "export_data": False, "import_data": False, "settings_access": False, "financial_reports": False, "gst_reports": False}},
        {"name": "Auditor", "description": "Read-only + audit trail", "permissions": {"view_all_data": True, "edit_all_data": False, "delete_entries": False, "approve_vouchers": False, "discount_override": False, "report_access": True, "stock_adjustment": False, "export_data": True, "import_data": False, "settings_access": False, "financial_reports": True, "gst_reports": True}},
    ]},
    "notifications": {
        "whatsapp": {"enabled": False, "api_key": ""},
        "sms": {"enabled": False, "provider": "", "api_key": ""},
        "email": {"enabled": True, "smtp_host": "", "smtp_port": 587, "smtp_user": "", "smtp_password": "", "sender_email": "", "sender_name": ""},
        "events": {"invoice_sent": True, "payment_reminder": True, "order_update": True, "payment_received": True, "invoice_due": True, "delivery_note": False, "credit_note": True},
    },
    "backup": {"backup": {"auto_backup": True, "backup_frequency": "daily", "google_drive": False, "onedrive": False, "local_backup_path": "./backups", "retention_days": 30}, "offline": {"enabled": False, "sync_on_reconnect": True}, "sync": {"multi_device_sync": False, "local_network_sync": False}},
    "reports": {"filters": {"date_range": "this_month", "hide_profit_from_staff": False, "default_page_size": 25}, "favorites": [], "scheduled": {"enabled": False, "frequency": "weekly", "recipients": [], "report_types": []}, "export_formats": ["excel", "pdf", "csv"]},
    "pos": {"thermal_printer": {"printer_name": "", "printer_type": "thermal", "paper_width": 58, "auto_cut": True}, "barcode_scanner": False, "customer_display": {"enabled": False, "display_type": "led"}, "fast_billing_mode": False, "offline_pos": False, "default_payment_mode": "cash"},
    "automations": {"reminders": {"payment_reminder": True, "due_date_reminder_days": 3, "overdue_reminder_days": 1}, "gst": {"filing_alerts": True, "alert_days_before": 7, "auto_gstr1": False, "auto_gstr3b": False}, "recurring_invoices": {"enabled": False, "generate_days_before": 1}, "stock_alerts": {"low_stock_alert": True, "low_stock_threshold": 10, "out_of_stock_alert": True}, "accounting": {"auto_post_gl": True, "reconcile_on_payment": True}},
    "security": {"two_factor": {"enabled": False, "method": "totp"}, "pin_lock": {"enabled": False, "timeout_minutes": 5}, "device_restrictions": {"enabled": False, "max_devices": 5}, "login_history": True, "ip_restrictions": [], "sessions": {"timeout_minutes": 480, "max_concurrent_sessions": 3}},
    "integrations": {"tally": {"enabled": False, "sync_direction": "import", "last_sync": None}, "excel_import_export": True, "shopify": {"enabled": False, "store_url": None, "api_key": None}, "woocommerce": {"enabled": False, "store_url": None, "api_key": None}, "amazon": {"enabled": False, "store_url": None, "api_key": None}, "ondc": False, "webhooks": []},
    "developer": {"api_keys": [], "webhook_endpoints": [], "event_logs_enabled": True, "queue_monitor_enabled": True, "background_jobs_enabled": True, "audit_log_retention_days": 365},
}


def upgrade():
    op.create_table(
        'tenant_settings',
        Column('id', Integer, primary_key=True, autoincrement=True),
        Column('tenant_id', String(64), index=True, nullable=False, unique=True),
        Column('business', JSON, default=DEFAULT_SETTINGS['business']),
        Column('invoice', JSON, default=DEFAULT_SETTINGS['invoice']),
        Column('gst', JSON, default=DEFAULT_SETTINGS['gst']),
        Column('accounting', JSON, default=DEFAULT_SETTINGS['accounting']),
        Column('inventory', JSON, default=DEFAULT_SETTINGS['inventory']),
        Column('payments', JSON, default=DEFAULT_SETTINGS['payments']),
        Column('roles', JSON, default=DEFAULT_SETTINGS['roles']),
        Column('notifications', JSON, default=DEFAULT_SETTINGS['notifications']),
        Column('backup', JSON, default=DEFAULT_SETTINGS['backup']),
        Column('reports', JSON, default=DEFAULT_SETTINGS['reports']),
        Column('pos', JSON, default=DEFAULT_SETTINGS['pos']),
        Column('automations', JSON, default=DEFAULT_SETTINGS['automations']),
        Column('security', JSON, default=DEFAULT_SETTINGS['security']),
        Column('integrations', JSON, default=DEFAULT_SETTINGS['integrations']),
        Column('developer', JSON, default=DEFAULT_SETTINGS['developer']),
        Column('created_at', DateTime, default=datetime.utcnow),
        Column('updated_at', DateTime, default=datetime.utcnow),
        UniqueConstraint('tenant_id', name='uq_tenant_settings_tenant'),
    )


def downgrade():
    op.drop_table('tenant_settings')