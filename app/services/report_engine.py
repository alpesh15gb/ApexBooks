"""
Enterprise Report Query Engine

Handles:
- Data aggregation and computation
- Multi-dimensional filtering
- Pre-aggregated snapshots
- Caching strategy
- Drill-down navigation
"""

import json
import hashlib
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from sqlalchemy import func, and_, or_, text
from sqlalchemy.orm import Session
from app.core.exceptions import APIError


class ReportMetrics:
    """Tracks report generation metrics for performance monitoring."""

    def __init__(self):
        self.query_time_ms = 0
        self.aggregation_time_ms = 0
        self.row_count = 0
        self.cache_hit = False

    def to_dict(self):
        return {
            "query_time_ms": round(self.query_time_ms, 2),
            "aggregation_time_ms": round(self.aggregation_time_ms, 2),
            "total_time_ms": round(self.query_time_ms + self.aggregation_time_ms, 2),
            "row_count": self.row_count,
            "cache_hit": self.cache_hit,
        }


class ReportDefinition:
    """Schema for a report definition including filters, columns, grouping."""

    def __init__(
        self,
        report_type: str,
        name: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        filters: Optional[dict] = None,
        group_by: Optional[list[str]] = None,
        sort_by: Optional[list[dict]] = None,
        page: int = 1,
        page_size: int = 50,
    ):
        self.report_type = report_type
        self.name = name
        self.from_date = from_date
        self.to_date = to_date
        self.filters = filters or {}
        self.group_by = group_by or []
        self.sort_by = sort_by or []
        self.page = page
        self.page_size = min(page_size, 500)

    def cache_key(self, tenant_id: str) -> str:
        """Generate a unique cache key for this report configuration."""
        raw = json.dumps({
            "tenant_id": tenant_id,
            "report_type": self.report_type,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "filters": self.filters,
            "group_by": self.group_by,
            "sort_by": self.sort_by,
            "page": self.page,
            "page_size": self.page_size,
        }, sort_keys=True)
        return f"report:{hashlib.md5(raw.encode()).hexdigest()}"


class ReportQueryEngine:
    """Main engine for executing report queries with optimal performance."""

    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.metrics = ReportMetrics()

    # ── Financial Reports ──────────────────────────────────────────

    def profit_loss(self, params: ReportDefinition) -> dict:
        """Profit & Loss statement with grouped income/expense accounts."""
        import time; t0 = time.time()
        from app.models.accounting import GLEntryModel, InvoiceModel
        from app.models.e2e import AccountModel
        from app.services.trial_balance_service import get_account_balances, _classify_account_type

        accounts_map = {r.code: r.account_type for r in self.db.query(AccountModel).filter_by(
            tenant_id=self.tenant_id, is_active=True).all()}

        # Parse period
        period_month = None
        period_year = None
        if params.from_date:
            period_year = int(params.from_date[:4])
            period_month = int(params.from_date[5:7])

        balances = get_account_balances(self.db, self.tenant_id, period_month, period_year, account_types=accounts_map)
        self.metrics.query_time_ms = (time.time() - t0) * 1000

        income = [b for b in balances if _classify_account_type(b['account_type']) == 'income']
        expenses = [b for b in balances if _classify_account_type(b['account_type']) == 'expense']
        gross_income = sum(b['balance'] for b in income)
        total_expenses = sum(b['balance'] for b in expenses)
        net_profit = gross_income - total_expenses
        self.metrics.row_count = len(income) + len(expenses)

        return {
            "report_name": "Profit & Loss",
            "period": f"{params.from_date or 'All time'} to {params.to_date or 'Present'}",
            "income": income,
            "expenses": expenses,
            "gross_income": round(gross_income, 2),
            "total_expenses": round(total_expenses, 2),
            "net_profit": round(net_profit, 2),
            "metrics": self.metrics.to_dict(),
        }

    def balance_sheet(self, params: ReportDefinition) -> dict:
        """Balance sheet with assets, liabilities, equity."""
        import time; t0 = time.time()
        from app.api.v1.accounts.router import _classify_account_type
        from app.models.e2e import AccountModel
        from app.services.trial_balance_service import get_account_balances

        accounts_map = {r.code: r.account_type for r in self.db.query(AccountModel).filter_by(
            tenant_id=self.tenant_id, is_active=True).all()}

        period_month = int(params.from_date[5:7]) if params.from_date else None
        period_year = int(params.from_date[:4]) if params.from_date else None

        balances = get_account_balances(self.db, self.tenant_id, period_month, period_year, account_types=accounts_map)
        self.metrics.query_time_ms = (time.time() - t0) * 1000

        assets = [b for b in balances if _classify_account_type(b['account_type']) == 'asset']
        liabilities = [b for b in balances if _classify_account_type(b['account_type']) == 'liability']
        equity = [b for b in balances if _classify_account_type(b['account_type']) == 'equity']
        income_balances = [b for b in balances if _classify_account_type(b['account_type']) == 'income']
        expense_balances = [b for b in balances if _classify_account_type(b['account_type']) == 'expense']
        net_profit = sum(b['balance'] for b in income_balances) - sum(b['balance'] for b in expense_balances)

        total_assets = round(sum(b['balance'] for b in assets), 2)
        total_liabilities = round(sum(b['balance'] for b in liabilities), 2)
        total_equity = round(sum(b['balance'] for b in equity) + net_profit, 2)
        self.metrics.row_count = len(assets) + len(liabilities) + len(equity)

        return {
            "report_name": "Balance Sheet",
            "as_of_date": params.to_date or str(date.today()),
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
            "net_profit": round(net_profit, 2),
            "balance_sheet_balanced": abs(total_assets - total_liabilities - total_equity) < 0.01,
            "metrics": self.metrics.to_dict(),
        }

    def trial_balance(self, params: ReportDefinition) -> dict:
        """Trial balance with debit/credit totals."""
        import time; t0 = time.time()
        from app.models.accounting import GLEntryModel
        from app.services.trial_balance_service import verify_trial_balance, get_account_balances

        period_month = int(params.from_date[5:7]) if params.from_date else None
        period_year = int(params.from_date[:4]) if params.from_date else None

        # Get all unique accounts in GL
        accounts = self.db.query(GLEntryModel.account).filter_by(
            tenant_id=self.tenant_id
        ).distinct().all()
        account_codes = [r[0] for r in accounts]

        # Get balances
        from app.models.e2e import AccountModel
        accounts_map = {r.code: r.account_type for r in self.db.query(AccountModel).filter_by(
            tenant_id=self.tenant_id, is_active=True).all()}

        balances = get_account_balances(self.db, self.tenant_id, period_month, period_year, account_types=accounts_map)
        verification = verify_trial_balance(self.db, self.tenant_id, period_month, period_year)
        self.metrics.query_time_ms = (time.time() - t0) * 1000
        self.metrics.row_count = len(balances)

        return {
            "report_name": "Trial Balance",
            "period": f"{params.from_date or 'All time'} to {params.to_date or 'Present'}",
            "accounts": balances,
            "total_debit": round(sum(b['total_debit'] for b in balances), 2),
            "total_credit": round(sum(b['total_credit'] for b in balances), 2),
            "verification": verification,
            "metrics": self.metrics.to_dict(),
        }

    def general_ledger(self, params: ReportDefinition) -> dict:
        """General ledger with all entries, filterable by account."""
        import time; t0 = time.time()
        from app.models.accounting import GLEntryModel

        q = self.db.query(GLEntryModel).filter_by(tenant_id=self.tenant_id)

        # Apply filters
        account_filter = params.filters.get('account')
        if account_filter:
            q = q.filter(GLEntryModel.account == account_filter)

        party_filter = params.filters.get('party_id')
        if party_filter:
            q = q.filter(GLEntryModel.party_id == party_filter)

        if params.from_date:
            q = q.filter(GLEntryModel.posting_date >= params.from_date)
        if params.to_date:
            q = q.filter(GLEntryModel.posting_date <= params.to_date)

        voucher_filter = params.filters.get('voucher_type')
        if voucher_filter:
            q = q.filter(GLEntryModel.voucher_type == voucher_filter)

        # Sort and paginate
        total = q.count()
        q = q.order_by(GLEntryModel.posting_date.desc(), GLEntryModel.id.desc())
        q = q.offset((params.page - 1) * params.page_size).limit(params.page_size)

        entries = []
        for r in q.all():
            entries.append({
                "id": r.id,
                "date": str(r.posting_date),
                "account": r.account,
                "party_id": r.party_id,
                "voucher_type": r.voucher_type,
                "voucher_id": r.voucher_id,
                "debit": float(r.debit or 0),
                "credit": float(r.credit or 0),
                "remarks": r.remarks,
            })

        running_balance = 0
        for e in reversed(entries):
            running_balance += e['debit'] - e['credit']
            e['balance'] = round(running_balance, 2)

        self.metrics.query_time_ms = (time.time() - t0) * 1000
        self.metrics.row_count = len(entries)

        return {
            "report_name": "General Ledger",
            "period": f"{params.from_date or 'All time'} to {params.to_date or 'Present'}",
            "account_filter": account_filter,
            "entries": entries,
            "total_entries": total,
            "total_debit": round(sum(e['debit'] for e in entries), 2),
            "total_credit": round(sum(e['credit'] for e in entries), 2),
            "page": params.page,
            "page_size": params.page_size,
            "total_pages": max(1, (total + params.page_size - 1) // params.page_size),
            "metrics": self.metrics.to_dict(),
        }

    # ── Aging Reports ──────────────────────────────────────────────

    def aging_report(self, params: ReportDefinition, direction: str = 'receivable') -> dict:
        """Aging report for receivables or payables."""
        import time; t0 = time.time()
        from app.models.accounting import InvoiceModel

        kind = 'sales' if direction == 'receivable' else 'purchase'
        invoices = self.db.query(InvoiceModel).filter(
            InvoiceModel.tenant_id == self.tenant_id,
            InvoiceModel.invoice_kind == kind,
            InvoiceModel.status.in_(['Submitted', 'Part Paid', 'Paid']),
        ).all()

        today = date.today()
        buckets = {"0-30": [], "31-60": [], "61-90": [], "90+": []}

        for inv in invoices:
            outstanding = float(inv.grand_total - inv.amount_paid)
            if outstanding <= 0:
                continue

            if inv.due_date:
                days_overdue = (today - inv.due_date).days
            else:
                days_overdue = (today - inv.invoice_date).days - 30

            if days_overdue <= 0:
                bucket = "0-30"
            elif days_overdue <= 30:
                bucket = "0-30"
            elif days_overdue <= 60:
                bucket = "31-60"
            elif days_overdue <= 90:
                bucket = "61-90"
            else:
                bucket = "90+"

            buckets[bucket].append({
                "invoice_id": inv.invoice_id,
                "invoice_number": inv.invoice_number,
                "party_name": inv.party_id,
                "invoice_date": str(inv.invoice_date),
                "due_date": str(inv.due_date) if inv.due_date else "",
                "amount": float(inv.grand_total),
                "outstanding": round(outstanding, 2),
                "days_overdue": max(0, days_overdue),
            })

        self.metrics.query_time_ms = (time.time() - t0) * 1000
        self.metrics.row_count = sum(len(v) for v in buckets.values())

        return {
            "report_name": f"{'Receivables' if direction == 'receivable' else 'Payables'} Aging",
            "as_of_date": str(today),
            "buckets": {k: {"items": v, "total": round(sum(i['outstanding'] for i in v), 2)} for k, v in buckets.items()},
            "grand_total": round(sum(i['outstanding'] for v in buckets.values() for i in v), 2),
            "metrics": self.metrics.to_dict(),
        }

    # ── GST Reports ────────────────────────────────────────────────

    def gst_summary(self, params: ReportDefinition) -> dict:
        """GST summary report with input/output tax breakups."""
        import time; t0 = time.time()
        from app.models.accounting import InvoiceModel

        month = int(params.filters.get('month', date.today().month))
        year = int(params.filters.get('year', date.today().year))

        # Sales (output GST)
        sales = self.db.query(
            func.coalesce(func.sum(InvoiceModel.total_cgst), 0).label('cgst'),
            func.coalesce(func.sum(InvoiceModel.total_sgst), 0).label('sgst'),
            func.coalesce(func.sum(InvoiceModel.total_igst), 0).label('igst'),
            func.coalesce(func.sum(InvoiceModel.total_cess), 0).label('cess'),
            func.coalesce(func.sum(InvoiceModel.subtotal), 0).label('taxable'),
        ).filter(
            InvoiceModel.tenant_id == self.tenant_id,
            InvoiceModel.invoice_kind == 'sales',
            InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid']),
            func.extract('month', InvoiceModel.invoice_date) == month,
            func.extract('year', InvoiceModel.invoice_date) == year,
        ).first()

        # Purchases (input GST / ITC)
        purchases = self.db.query(
            func.coalesce(func.sum(InvoiceModel.total_cgst), 0).label('cgst'),
            func.coalesce(func.sum(InvoiceModel.total_sgst), 0).label('sgst'),
            func.coalesce(func.sum(InvoiceModel.total_igst), 0).label('igst'),
            func.coalesce(func.sum(InvoiceModel.total_cess), 0).label('cess'),
            func.coalesce(func.sum(InvoiceModel.subtotal), 0).label('taxable'),
        ).filter(
            InvoiceModel.tenant_id == self.tenant_id,
            InvoiceModel.invoice_kind == 'purchase',
            InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid']),
            func.extract('month', InvoiceModel.invoice_date) == month,
            func.extract('year', InvoiceModel.invoice_date) == year,
        ).first()

        def to_float(v):
            return round(float(v or 0), 2)

        output = {
            "taxable": to_float(sales.taxable),
            "cgst": to_float(sales.cgst),
            "sgst": to_float(sales.sgst),
            "igst": to_float(sales.igst),
            "cess": to_float(sales.cess),
            "total_tax": to_float(sales.cgst + sales.sgst + sales.igst + sales.cess),
        }
        input_ = {
            "taxable": to_float(purchases.taxable),
            "cgst": to_float(purchases.cgst),
            "sgst": to_float(purchases.sgst),
            "igst": to_float(purchases.igst),
            "cess": to_float(purchases.cess),
            "total_itc": to_float(purchases.cgst + purchases.sgst + purchases.igst + purchases.cess),
        }
        net_payable = round(output['total_tax'] - input_['total_itc'], 2)

        self.metrics.query_time_ms = (time.time() - t0) * 1000

        return {
            "report_name": "GST Summary",
            "period": f"{year}-{month:02d}",
            "output_gst": output,
            "input_gst_itc": input_,
            "net_gst_payable": net_payable,
            "metrics": self.metrics.to_dict(),
        }

    # ── HSN/SAC Summary ────────────────────────────────────────────

    def hsn_summary(self, params: ReportDefinition) -> dict:
        """HSN/SAC wise summary of sales/purchases."""
        import time; t0 = time.time()
        from app.models.accounting import InvoiceLineModel, InvoiceModel

        q = self.db.query(
            InvoiceLineModel.hsn_code,
            func.coalesce(func.sum(InvoiceLineModel.quantity), 0).label('quantity'),
            func.coalesce(func.sum(InvoiceLineModel.taxable_value), 0).label('taxable'),
            func.coalesce(func.sum(InvoiceLineModel.cgst_amount + InvoiceLineModel.sgst_amount + InvoiceLineModel.igst_amount), 0).label('tax'),
        ).join(
            InvoiceModel, InvoiceLineModel.invoice_pk == InvoiceModel.id
        ).filter(
            InvoiceModel.tenant_id == self.tenant_id,
            InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid']),
            InvoiceLineModel.hsn_code != None,
        )

        kind_filter = params.filters.get('invoice_kind')
        if kind_filter:
            q = q.filter(InvoiceModel.invoice_kind == kind_filter)

        if params.from_date:
            q = q.filter(InvoiceModel.invoice_date >= params.from_date)
        if params.to_date:
            q = q.filter(InvoiceModel.invoice_date <= params.to_date)

        q = q.group_by(InvoiceLineModel.hsn_code).order_by(InvoiceLineModel.hsn_code)

        rows = []
        for r in q.all():
            rows.append({
                "hsn_code": r.hsn_code,
                "quantity": float(r.quantity or 0),
                "taxable_value": round(float(r.taxable or 0), 2),
                "tax_amount": round(float(r.tax or 0), 2),
            })

        self.metrics.query_time_ms = (time.time() - t0) * 1000
        self.metrics.row_count = len(rows)

        return {
            "report_name": "HSN/SAC Summary",
            "period": f"{params.from_date or 'All time'} to {params.to_date or 'Present'}",
            "items": rows,
            "total_taxable": round(sum(r['taxable_value'] for r in rows), 2),
            "total_tax": round(sum(r['tax_amount'] for r in rows), 2),
            "metrics": self.metrics.to_dict(),
        }

    # ── Sales/Purchase Reports ─────────────────────────────────────

    def sales_by_customer(self, params: ReportDefinition) -> dict:
        """Sales aggregated by customer."""
        import time; t0 = time.time()
        from app.models.accounting import InvoiceModel

        q = self.db.query(
            InvoiceModel.party_id,
            InvoiceModel.party_gstin,
            func.count().label('invoice_count'),
            func.coalesce(func.sum(InvoiceModel.subtotal), 0).label('total_taxable'),
            func.coalesce(func.sum(InvoiceModel.grand_total), 0).label('total_amount'),
        ).filter(
            InvoiceModel.tenant_id == self.tenant_id,
            InvoiceModel.invoice_kind == 'sales',
            InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid']),
        )

        if params.from_date:
            q = q.filter(InvoiceModel.invoice_date >= params.from_date)
        if params.to_date:
            q = q.filter(InvoiceModel.invoice_date <= params.to_date)

        q = q.group_by(InvoiceModel.party_id, InvoiceModel.party_gstin).order_by(func.sum(InvoiceModel.grand_total).desc())

        rows = [{
            "party_id": r.party_id,
            "gstin": r.party_gstin,
            "invoice_count": r.invoice_count,
            "total_taxable": round(float(r.total_taxable or 0), 2),
            "total_amount": round(float(r.total_amount or 0), 2),
        } for r in q.all()]

        self.metrics.query_time_ms = (time.time() - t0) * 1000
        self.metrics.row_count = len(rows)

        return {
            "report_name": "Sales by Customer",
            "period": f"{params.from_date or 'All time'} to {params.to_date or 'Present'}",
            "rows": rows,
            "grand_total": round(sum(r['total_amount'] for r in rows), 2),
            "metrics": self.metrics.to_dict(),
        }

    # ── Drill-down ──────────────────────────────────────────────────

    def drill_down(self, report_type: str, row_id: str, level: str = 'details') -> dict:
        """Drill down from a report row to underlying data."""
        from app.models.accounting import InvoiceModel, GLEntryModel, InvoiceLineModel

        if report_type == 'sales_by_customer' and level == 'invoices':
            invoices = self.db.query(InvoiceModel).filter_by(
                tenant_id=self.tenant_id, party_id=row_id, invoice_kind='sales'
            ).filter(
                InvoiceModel.status.in_(['Submitted', 'Paid', 'Part Paid'])
            ).order_by(InvoiceModel.invoice_date.desc()).all()

            return {
                "level": "invoices",
                "party_id": row_id,
                "invoices": [{
                    "invoice_id": inv.invoice_id,
                    "invoice_number": inv.invoice_number,
                    "date": str(inv.invoice_date),
                    "grand_total": float(inv.grand_total),
                    "status": inv.status,
                } for inv in invoices],
            }

        elif report_type == 'general_ledger' and level == 'voucher':
            entries = self.db.query(GLEntryModel).filter_by(
                tenant_id=self.tenant_id,
                voucher_id=row_id,
            ).order_by(GLEntryModel.id).all()

            return {
                "level": "voucher",
                "voucher_id": row_id,
                "entries": [{
                    "account": e.account,
                    "debit": float(e.debit or 0),
                    "credit": float(e.credit or 0),
                    "remarks": e.remarks,
                } for e in entries],
            }

        elif report_type == 'invoice' and level == 'lines':
            from app.models.accounting import InvoiceLineModel
            lines = self.db.query(InvoiceLineModel).join(
                InvoiceModel, InvoiceLineModel.invoice_pk == InvoiceModel.id
            ).filter(
                InvoiceModel.tenant_id == self.tenant_id,
                InvoiceModel.invoice_id == row_id,
            ).order_by(InvoiceLineModel.line_no).all()

            return {
                "level": "lines",
                "invoice_id": row_id,
                "lines": [{
                    "item_name": l.item_name,
                    "hsn_code": l.hsn_code,
                    "quantity": float(l.quantity),
                    "unit_price": float(l.unit_price),
                    "taxable_value": float(l.taxable_value),
                    "gst_rate": float(l.gst_rate),
                } for l in lines],
            }

        return {"level": level, "data": "No drill-down available for this report type"}

    # ── Execute ─────────────────────────────────────────────────────

    def execute(self, params: ReportDefinition) -> dict:
        """Execute a report by type."""
        dispatch = {
            "profit_loss": self.profit_loss,
            "balance_sheet": self.balance_sheet,
            "trial_balance": self.trial_balance,
            "general_ledger": self.general_ledger,
            "receivables_aging": lambda p: self.aging_report(p, 'receivable'),
            "payables_aging": lambda p: self.aging_report(p, 'payable'),
            "gst_summary": self.gst_summary,
            "hsn_summary": self.hsn_summary,
            "sales_by_customer": self.sales_by_customer,
        }

        handler = dispatch.get(params.report_type)
        if not handler:
            raise APIError('INVALID_REPORT', f'Unknown report type: {params.report_type}', status_code=400)
        return handler(params)
