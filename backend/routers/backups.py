import json
from accounting import company_for, company_obj, current_user, db, obj
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from models import (
    AuditEvent, BankAccount, BankMatchAllocation, BankReconciliationReview, BankStatementLine,
    CompanyMember, DocumentConversion, Journal, JournalLine, JournalReversal, LedgerAccount,
    NumberSeries, PaymentAllocation, PaymentSplitAllocation, PeriodLock, Record, RecordPosting,
    StockMovement, User,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


router = APIRouter()


@router.get('/api/companies/{company_id}/data-export.json')
def company_data_export(company_id: str, user: User = Depends(current_user), session: Session = Depends(db)):
    import book_services as services
    company_for(company_id,user,session)
    if hasattr(services,'DocumentAttachment') and session.scalar(select(services.DocumentAttachment.id).where(services.DocumentAttachment.company_id==company_id).limit(1)):
        raise HTTPException(409,'COMPLETE_BACKUP_REQUIRED: This company retains receipt files. Use /api/companies/'+company_id+'/backup-exports to create a complete portable backup.',headers={'X-Apex-Error':'COMPLETE_BACKUP_REQUIRED'})
    return company_data_export_payload(company_id,user,session)


def company_data_export_payload(company_id,user,session):
    from routers.banking import reconciliation_review_obj
    from routers.companies import get_preferences
    company = company_for(company_id, user, session)
    if company.owner_id != user.id: raise HTTPException(403, 'Only the owner can export all company data')
    accounts = list(session.scalars(select(LedgerAccount).where(LedgerAccount.company_id == company_id)))
    journals = list(session.scalars(select(Journal).where(Journal.company_id == company_id)))
    lines = list(session.scalars(select(JournalLine).where(JournalLine.company_id == company_id)))
    records = list(session.scalars(select(Record).where(Record.company_id == company_id)))
    postings = list(session.scalars(select(RecordPosting).where(RecordPosting.company_id == company_id)))
    conversions = list(session.scalars(select(DocumentConversion).where(DocumentConversion.company_id == company_id)))
    allocations = list(session.scalars(select(PaymentAllocation).where(PaymentAllocation.company_id == company_id)))
    allocations += list(session.scalars(select(PaymentSplitAllocation).where(PaymentSplitAllocation.company_id == company_id)))
    bank_accounts = list(session.scalars(select(BankAccount).where(BankAccount.company_id == company_id)))
    statement = list(session.scalars(select(BankStatementLine).where(BankStatementLine.company_id == company_id)))
    bank_match_allocations = list(session.scalars(select(BankMatchAllocation).where(BankMatchAllocation.company_id == company_id)))
    reconciliation_reviews = list(session.scalars(select(BankReconciliationReview).where(BankReconciliationReview.company_id == company_id)))
    stock_movements = list(session.scalars(select(StockMovement).where(StockMovement.company_id == company_id)))
    events = list(session.scalars(select(AuditEvent).where(AuditEvent.company_id == company_id)))
    series = list(session.scalars(select(NumberSeries).where(NumberSeries.company_id == company_id)))
    members = list(session.scalars(select(CompanyMember).where(CompanyMember.company_id == company_id)))
    period_lock = session.get(PeriodLock, company_id)
    payload = {'schema_version': 7, 'exported_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'single_company_data_export', 'company': company_obj(company, session, user),
        'preferences': get_preferences(company_id, user, session),
        'members': [{'email': session.get(User, m.user_id).email, 'role': m.role} for m in members],
        'records': [{**obj(r), 'company_id': company_id} for r in records],
        'accounts': [{'id': a.id, 'code': a.code, 'name': a.name, 'category': a.category} for a in accounts],
        'journals': [{'id': j.id, 'date': j.date.isoformat(), 'reference': j.reference, 'memo': j.memo} for j in journals],
        'journal_lines': [{'journal_id': l.journal_id, 'account_id': l.account_id, 'debit': str(l.debit), 'credit': str(l.credit)} for l in lines],
        'journal_reversals': [{'original_id': r.original_id, 'reversal_id': r.reversal_id} for r in session.scalars(select(JournalReversal).where(JournalReversal.company_id == company_id))],
        'record_postings': [{'record_id': p.record_id, 'journal_id': p.journal_id} for p in postings],
        'document_conversions': [{'source_record_id': c.source_record_id, 'target_record_id': c.target_record_id} for c in conversions],
        'payment_allocations': [{'payment_id': a.payment_id, 'document_id': a.document_id, 'amount': str(a.amount)} for a in allocations],
        'bank_accounts': [{'id': b.id, 'ledger_account_id': b.ledger_account_id, 'name': b.name, 'account_hint': b.account_hint} for b in bank_accounts],
        'bank_statement_lines': [{'id': l.id, 'bank_account_id': l.bank_account_id or 'default', 'date': l.date.isoformat(), 'description': l.description, 'reference': l.reference, 'amount': str(l.amount), 'matched_record_id': l.matched_record_id} for l in statement],
        'bank_match_allocations': [{'id': a.id, 'statement_line_id': a.statement_line_id, 'record_id': a.record_id, 'amount': str(a.amount)} for a in bank_match_allocations],
        'bank_reconciliation_reviews': [reconciliation_review_obj(review) for review in reconciliation_reviews],
        'stock_movements': [{'id': movement.id, 'item_id': movement.item_id, 'source_record_id': movement.source_record_id,
            'line_index': movement.line_index, 'date': movement.date.isoformat(), 'quantity': str(movement.quantity),
            'cost_value': str(movement.cost_value) if movement.cost_value is not None else None} for movement in stock_movements],
        'audit_events': [{'id': e.id, 'actor': session.get(User, e.actor_id).email, 'occurred_at': e.occurred_at.isoformat(), 'action': e.action, 'entity_type': e.entity_type, 'entity_id': e.entity_id, 'details': e.details} for e in events],
        'number_series': [{'kind': s.kind, 'financial_year': s.financial_year, 'prefix': s.prefix, 'next_number': s.next_number} for s in series],
        'locked_through': period_lock.locked_through.isoformat() if period_lock else None}
    from company_restore import pack
    return Response(json.dumps(pack(payload), allow_nan=False), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="company-data.json"'})
