"""Shared interface for feature installers, migration tools, and legacy Python callers."""
import httpx
from accounting import (
    APPLICATION_KINDS, DEFAULT_PREFIXES, DOCUMENTS, KINDS, NUMBERED_KINDS, POSTED_KINDS,
    SYSTEM_ACCOUNTS, applied_total, applied_totals_by_document, audit, audit_changes,
    bank_account_for, calculate, company_for, company_obj, current_user, db, lock_company,
    master_name_matches, member_role, money, next_document_number,
    normalize_document_tax_identifiers, obj, payment_key, posting_account, posting_lines,
    require_open_period, require_write, source_return_itc, system_account, validate_pos_payment,
    value_stock_lines,
)
from build_info import BUILD_REVISION
from business_calendar import business_today
from datetime import date as DateType
from fastapi import Response
from invoice_requirements import validate_outward_invoice_fields
from models import (
    AuditEvent, AuthSession, BankAccount, BankImportReceipt, BankMatchAllocation,
    BankReconciliationReview, BankStatementLine, Base, Company, CompanyMember, CompanyPreference,
    CompanyTaxProfile, DATABASE_URL, DocumentConversion, IdempotencyKey, Journal, JournalLine,
    JournalReversal, LedgerAccount, MasterImportReceipt, NumberSeries, PaymentAllocation,
    PaymentSplitAllocation, PeriodLock, Record, RecordPosting, SECRET, StockMovement, User,
    _DUMMY_PASSWORD_HASH, engine, passwords, security,
)
from routers.auth import change_password, login, logout, logout_other_sessions, register
from routers.backups import company_data_export, company_data_export_payload
from routers.banking import (
    add_bank_match_allocation, bank_import_receipt, bank_reconciliation,
    bank_reconciliation_reviews, bank_record_amount, bank_record_for_match, bank_statement,
    cash_book, create_account, create_bank_account, create_journal, export_cash_book,
    get_period_lock, import_bank_statement, list_accounts, list_bank_accounts, list_journals,
    match_bank_statement, reconciliation_review_obj, remove_bank_match_allocation, reverse_journal,
    save_bank_reconciliation_review, set_period_lock, unmatch_bank_statement,
)
from routers.companies import (
    BANK_FIELDS, DocumentBranding, add_member, audit_events, branding_for, companies,
    create_company, get_branding, get_preferences, list_members, list_number_series, patch_branding,
    remove_member, set_branding, set_number_series, set_preferences, update_company,
    with_payment_details,
)
from routers.documents import (
    apply_advance, apply_advance_in_transaction, client_record_data, compact_record_data,
    create_record, document_pdf, get_record, record_status, records, resolve_party, save_record,
    validate_active_references, validate_outward_document_number,
)
from routers.gst import export_gst, gst_report
from routers.inventory import (
    adjustment_stock, count_snapshot, export_items, export_stock, get_stock_count, item_report,
    item_stock_movements, pos_stock_summary, post_adjustment, post_opening_stock,
    post_stock_adjustment, post_stock_count, stock_report, validate_count_stock,
)
from routers.masters import (
    VyaparImportInput, export_masters, import_masters, master_import_receipt, update_master,
    vyapar_archive, vyapar_full_posting, vyapar_import, vyapar_reconciliation,
)
from routers.ocr import ocr_configuration, ocr_purchase_draft, ocr_status
from routers.reports import (
    account_balances, account_movements, advances_report, advances_report_export, ageing_report,
    export, export_ageing, export_financial, export_parties, export_summary, export_table,
    export_transaction_register, financial_report, party_report, report_summary,
    transaction_register, trial_balance,
)
from schemas import (
    AccountInput, BankAccountInput, BankMatchAllocationInput, BookLabelInput, CompanyInput,
    CompanyPreferenceInput, CompanyUpdate, Credentials, JournalInput, JournalLineInput, LockInput,
    MasterImport, MasterRow, MatchInput, MemberInput, OcrInput, OpeningStockInput, PasswordChange,
    ReconciliationReviewInput, RecordInput, ReversalInput, SeriesInput, StatementImport,
    StatementInputLine, StockAdjustmentInput, StockCountInput, validate_item_image,
    validate_master_defaults,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from workflow_extensions import available_credit
