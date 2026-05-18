from datetime import date
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.exceptions import APIError
from app.models.accounting import GLEntryModel
from app.models.e2e import AccountModel


class OpeningBalanceService:
    """Handles opening balance journal entries for fiscal year start.

    Opening balances are posted as a special journal entry with voucher_type='opening_balance'.
    This allows the system to verify integrity (total debits = total credits).
    """

    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    def check_posted(self, fiscal_year: int) -> bool:
        """Check if opening balances have been posted for a fiscal year."""
        count = self.db.query(func.count(GLEntryModel.id)).filter_by(
            tenant_id=self.tenant_id,
            voucher_type='opening_balance',
            voucher_id=f'opening_{fiscal_year}',
        ).scalar()
        return count > 0

    def post_account_balance(self, account_code: str, amount: Decimal, fiscal_year: int, side: str = 'debit') -> dict:
        """Post opening balance for a single account.

        Args:
            account_code: Chart of accounts code
            amount: Opening balance amount
            fiscal_year: Fiscal year (e.g., 2026)
            side: 'debit' for asset/expense accounts, 'credit' for liability/income/equity

        Returns:
            dict with posting result
        """
        if amount <= 0:
            raise APIError('INVALID_AMOUNT', 'Opening balance amount must be positive', status_code=400)

        if side not in ('debit', 'credit'):
            raise APIError('INVALID_SIDE', 'Side must be debit or credit', status_code=400)

        # Validate account exists
        account = self.db.query(AccountModel).filter_by(
            tenant_id=self.tenant_id, code=account_code, is_active=True
        ).first()
        if not account:
            # Auto-create account if it doesn't exist
            from uuid import uuid4
            account = AccountModel(
                tenant_id=self.tenant_id,
                code=account_code,
                name=account_code,
                account_type='Asset' if side == 'debit' else 'Liability',
                is_active=True,
            )
            self.db.add(account)
            self.db.flush()

        posting_date = date(fiscal_year, 4, 1)  # Indian FY starts April 1
        voucher_id = f'opening_{fiscal_year}'

        gl = GLEntryModel(
            tenant_id=self.tenant_id,
            posting_date=posting_date,
            account=account_code,
            party_id=None,
            voucher_type='opening_balance',
            voucher_id=voucher_id,
            debit=amount if side == 'debit' else Decimal('0'),
            credit=amount if side == 'credit' else Decimal('0'),
            remarks=f'Opening balance FY {fiscal_year}: {account_code} ({side})',
        )
        self.db.add(gl)
        self.db.flush()

        return {
            'account_code': account_code,
            'amount': float(amount),
            'side': side,
            'posting_date': str(posting_date),
            'voucher_id': voucher_id,
        }

    def post_party_outstanding(self, party_id: str, party_name: str, amount: Decimal,
                                fiscal_year: int, party_type: str = 'Customer') -> dict:
        """Post opening balance for a party (customer/vendor outstanding).

        Creates both the party GL entry and the corresponding A/R or A/P entry.
        """
        if amount <= 0:
            raise APIError('INVALID_AMOUNT', 'Opening balance amount must be positive', status_code=400)

        posting_date = date(fiscal_year, 4, 1)
        voucher_id = f'opening_{fiscal_year}'

        if party_type == 'Customer':
            # Dr Accounts Receivable -> Cr Opening Balance Suspense
            ar_account = 'Accounts Receivable'
            gl1 = GLEntryModel(
                tenant_id=self.tenant_id, posting_date=posting_date,
                account=ar_account, party_id=party_id,
                voucher_type='opening_balance', voucher_id=voucher_id,
                debit=amount, credit=Decimal('0'),
                remarks=f'Opening outstanding: {party_name}',
            )
            self.db.add(gl1)
        else:
            # Dr Opening Balance Suspense -> Cr Accounts Payable
            ap_account = 'Accounts Payable'
            gl1 = GLEntryModel(
                tenant_id=self.tenant_id, posting_date=posting_date,
                account=ap_account, party_id=party_id,
                voucher_type='opening_balance', voucher_id=voucher_id,
                debit=Decimal('0'), credit=amount,
                remarks=f'Opening outstanding: {party_name}',
            )
            self.db.add(gl1)

        # Add contra entry to suspense
        suspense_acct = 'Opening Balance Suspense'
        gl2 = GLEntryModel(
            tenant_id=self.tenant_id, posting_date=posting_date,
            account=suspense_acct, party_id=None,
            voucher_type='opening_balance', voucher_id=voucher_id,
            debit=Decimal('0') if party_type == 'Customer' else amount,
            credit=amount if party_type == 'Customer' else Decimal('0'),
            remarks=f'Opening balance contra: {party_name}',
        )
        self.db.add(gl2)
        self.db.flush()

        return {
            'party_id': party_id,
            'party_name': party_name,
            'amount': float(amount),
            'party_type': party_type,
            'posting_date': str(posting_date),
        }

    def verify_and_finalize(self, fiscal_year: int) -> dict:
        """Verify opening balances are balanced and finalize.

        Checks that total debits = total credits for the opening entry.
        """
        from app.services.trial_balance_service import post_suspense_if_unbalanced

        voucher_id = f'opening_{fiscal_year}'
        balanced = post_suspense_if_unbalanced(self.db, self.tenant_id,
                                                date(fiscal_year, 4, 1),
                                                'opening_balance', voucher_id)

        # Get totals
        result = self.db.query(
            func.coalesce(func.sum(GLEntryModel.debit), Decimal('0')).label('total_debit'),
            func.coalesce(func.sum(GLEntryModel.credit), Decimal('0')).label('total_credit'),
        ).filter_by(
            tenant_id=self.tenant_id,
            voucher_type='opening_balance',
            voucher_id=voucher_id,
        ).first()

        return {
            'fiscal_year': fiscal_year,
            'total_debit': float(result.total_debit or 0),
            'total_credit': float(result.total_credit or 0),
            'balanced': balanced,
            'status': 'finalized' if balanced else 'imbalanced',
        }

    def get_opening_entries(self, fiscal_year: int) -> list[dict]:
        """Get all opening balance GL entries for a fiscal year."""
        entries = self.db.query(GLEntryModel).filter_by(
            tenant_id=self.tenant_id,
            voucher_type='opening_balance',
            voucher_id=f'opening_{fiscal_year}',
        ).order_by(GLEntryModel.id).all()

        return [{
            'id': e.id,
            'account': e.account,
            'party_id': e.party_id,
            'debit': float(e.debit or 0),
            'credit': float(e.credit or 0),
            'remarks': e.remarks,
        } for e in entries]


opening_balance_service = OpeningBalanceService
