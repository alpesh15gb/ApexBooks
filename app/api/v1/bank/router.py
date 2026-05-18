from fastapi import APIRouter, Depends
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.core.database import get_db
from app.core.exceptions import ok, APIError
from app.api.v1.deps import current_tenant
from app.models.accounting import GLEntryModel, InvoiceModel
from app.services.normalized_repository import normalized_repo, model_dict

router = APIRouter(prefix='/bank', tags=['Banking'])


@router.post('/accounts')
def create_bank_account(payload: dict, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Register a bank account for reconciliation."""
    from app.models.e2e import ResourceRecord
    from uuid import uuid4

    name = payload.get('name')
    account_number = payload.get('account_number')
    bank_name = payload.get('bank_name', '')
    if_type = payload.get('if_type', 'ifsc')  # ifsc or micr
    if_code = payload.get('if_code', '')

    if not name or not account_number:
        raise APIError('MISSING_FIELDS', 'Bank account name and number are required', status_code=400)

    rec = ResourceRecord(
        tenant_id=tenant_id,
        resource='bank_account',
        resource_id=str(uuid4()),
        payload={
            'name': name,
            'account_number': account_number,
            'bank_name': bank_name,
            'if_type': if_type,
            'if_code': if_code,
            'is_active': True,
        },
        status='active',
        txn_date=date.today(),
    )
    db.add(rec)
    db.flush()

    return ok({
        'bank_account_id': rec.resource_id,
        'name': name,
        'account_number': f'****{account_number[-4:]}',
    }, 'Bank account registered')


@router.get('/accounts')
def list_bank_accounts(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """List all registered bank accounts."""
    from app.models.e2e import ResourceRecord

    accounts = db.query(ResourceRecord).filter_by(
        tenant_id=tenant_id, resource='bank_account', is_deleted=False
    ).all()

    return ok({
        'bank_accounts': [
            {
                'bank_account_id': a.resource_id,
                'name': a.payload.get('name'),
                'account_number': f'****{a.payload.get("account_number", "")[-4:]}',
                'bank_name': a.payload.get('bank_name'),
                'if_code': a.payload.get('if_code'),
                'is_active': a.payload.get('is_active', True),
            }
            for a in accounts
        ]
    })


@router.post('/transactions/import')
def import_bank_transactions(payload: dict, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Import bank statement transactions for reconciliation.

    Accepts a list of transactions:
    [{"date": "2024-01-15", "narration": "NEFT/Payment", "debit": 5000, "credit": 0, "ref": "TXN123"}]
    """
    transactions = payload.get('transactions', [])
    bank_account_id = payload.get('bank_account_id')

    if not transactions:
        raise APIError('MISSING_TRANSACTIONS', 'No transactions provided', status_code=400)

    from app.models.e2e import ResourceRecord
    from uuid import uuid4

    imported = 0
    for txn in transactions:
        rec = ResourceRecord(
            tenant_id=tenant_id,
            resource='bank_transaction',
            resource_id=f'BT-{uuid4().hex[:12].upper()}',
            payload={
                'bank_account_id': bank_account_id,
                'date': str(txn.get('date', date.today())),
                'narration': txn.get('narration', ''),
                'debit': float(txn.get('debit', 0)),
                'credit': float(txn.get('credit', 0)),
                'ref_no': txn.get('ref', ''),
                'is_reconciled': False,
            },
            status='imported',
            txn_date=date.today(),
            amount=float(txn.get('debit', 0)) or float(txn.get('credit', 0)),
        )
        db.add(rec)
        imported += 1

    db.flush()

    return ok({'imported': imported, 'bank_account_id': bank_account_id}, 'Bank transactions imported')


@router.get('/transactions')
def list_transactions(tenant_id: str = Depends(current_tenant),
                      from_date: str | None = None,
                      to_date: str | None = None,
                      db: Session = Depends(get_db)):
    """List bank transactions."""
    from app.models.e2e import ResourceRecord

    q = db.query(ResourceRecord).filter_by(
        tenant_id=tenant_id, resource='bank_transaction', is_deleted=False
    ).order_by(ResourceRecord.txn_date.desc())

    if from_date:
        q = q.filter(ResourceRecord.txn_date >= from_date)
    if to_date:
        q = q.filter(ResourceRecord.txn_date <= to_date)

    transactions = []
    for rec in q.all():
        p = rec.payload
        transactions.append({
            'transaction_id': rec.resource_id,
            'date': str(rec.txn_date),
            'narration': p.get('narration', ''),
            'debit': p.get('debit', 0),
            'credit': p.get('credit', 0),
            'ref_no': p.get('ref_no', ''),
            'is_reconciled': p.get('is_reconciled', False),
            'matched_invoice_id': p.get('matched_invoice_id'),
        })

    return ok({'transactions': transactions, 'count': len(transactions)})


@router.post('/reconcile')
def reconcile_bank_statement(payload: dict, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Reconcile a bank transaction against a GL entry / invoice.

    payload: {
        "transaction_id": "BT-xxx",
        "matches": [
            {"invoice_id": "INV-xxx", "amount": 5000, "type": "payment"},
            ...
        ]
    }
    """
    transaction_id = payload.get('transaction_id')
    matches = payload.get('matches', [])

    if not transaction_id:
        raise APIError('MISSING_TRANSACTION', 'transaction_id is required', status_code=400)

    from app.models.e2e import ResourceRecord
    txn_rec = db.query(ResourceRecord).filter_by(
        tenant_id=tenant_id, resource='bank_transaction', resource_id=transaction_id
    ).first()
    if not txn_rec:
        raise APIError('TRANSACTION_NOT_FOUND', f'Bank transaction {transaction_id} not found', status_code=404)

    if txn_rec.payload.get('is_reconciled'):
        raise APIError('ALREADY_RECONCILED', f'Transaction {transaction_id} is already reconciled', status_code=400)

    total_matched = Decimal('0')
    match_details = []

    for match in matches:
        inv_id = match.get('invoice_id')
        amount = Decimal(str(match.get('amount', 0)))
        match_type = match.get('type', 'payment')

        if match_type == 'payment':
            # Match payment to invoice
            payment = db.query(PaymentModel := InvoiceModel).filter_by(
                tenant_id=tenant_id, invoice_id=inv_id
            ).first() if False else None

            from app.models.accounting import InvoiceModel
            inv = db.query(InvoiceModel).filter_by(
                tenant_id=tenant_id, invoice_id=inv_id
            ).first()

            if not inv:
                raise APIError('INVOICE_NOT_FOUND', f'Invoice {inv_id} not found', status_code=404)

            outstanding = Decimal(str(inv.grand_total - inv.amount_paid))
            if amount > outstanding:
                raise APIError('OVER_ALLOCATION',
                               f'Matched amount {amount} exceeds outstanding {outstanding} for {inv_id}',
                               status_code=400)

            total_matched += amount

            # Update invoice payment status
            inv.amount_paid = float(inv.amount_paid + amount)
            if inv.amount_paid >= float(inv.grand_total):
                inv.status = 'Paid'
                inv.payment_status = 'Paid'
            elif inv.amount_paid > 0:
                inv.status = 'Part Paid'
                inv.payment_status = 'Part Paid'

        match_details.append({'invoice_id': inv_id, 'amount': float(amount), 'type': match_type})

    # Verify total matches
    txn_debit = Decimal(str(txn_rec.payload.get('debit', 0)))
    txn_credit = Decimal(str(txn_rec.payload.get('credit', 0)))
    txn_amount = txn_debit or txn_credit

    if abs(txn_amount - total_matched) > Decimal('0.01'):
        raise APIError('MISMATCH',
                       f'Transaction amount {txn_amount} does not match total matched {total_matched}',
                       status_code=400)

    # Mark transaction as reconciled
    txn_rec.payload['is_reconciled'] = True
    txn_rec.payload['matches'] = match_details
    txn_rec.is_deleted = False

    # Create GL entries for reconciliation
    from app.models.accounting import GLEntryModel
    for match in matches:
        inv = db.query(InvoiceModel).filter_by(
            tenant_id=tenant_id, invoice_id=match['invoice_id']
        ).first()

        # Get bank account name for proper GL posting
        bank_acct = txn_rec.payload.get('name', 'Bank')

        if txn_rec.payload.get('debit', 0) > 0:
            # Incoming payment (debit in bank statement)
            db.add(GLEntryModel(
                tenant_id=tenant_id,
                posting_date=txn_rec.txn_date,
                account=bank_acct,
                party_id=inv.party_id if inv else None,
                voucher_type='bank_reconciliation',
                voucher_id=transaction_id,
                debit=match['amount'],
                credit=0,
                remarks=f'Bank reconciliation: {match["invoice_id"]}'
            ))
            db.add(GLEntryModel(
                tenant_id=tenant_id,
                posting_date=txn_rec.txn_date,
                account='Accounts Receivable',
                party_id=inv.party_id if inv else None,
                voucher_type='bank_reconciliation',
                voucher_id=transaction_id,
                debit=0,
                credit=match['amount'],
                remarks=f'Bank reconciliation: {match["invoice_id"]}'
            ))

    db.flush()

    return ok({
        'transaction_id': transaction_id,
        'status': 'Reconciled',
        'total_matched': float(total_matched),
        'matches': match_details,
    }, 'Bank transaction reconciled')


@router.get('/unreconciled')
def unreconciled_transactions(tenant_id: str = Depends(current_tenant),
                               from_date: str | None = None,
                               to_date: str | None = None,
                               db: Session = Depends(get_db)):
    """Get all unreconciled bank transactions."""
    from app.models.e2e import ResourceRecord

    q = db.query(ResourceRecord).filter_by(
        tenant_id=tenant_id, resource='bank_transaction',
    )

    if from_date:
        q = q.filter(ResourceRecord.txn_date >= from_date)
    if to_date:
        q = q.filter(ResourceRecord.txn_date <= to_date)

    # Filter: is_reconciled=False or not set
    unreconciled = []
    for rec in q.order_by(ResourceRecord.txn_date.desc()).all():
        p = rec.payload
        if not p.get('is_reconciled'):
            unreconciled.append({
                'transaction_id': rec.resource_id,
                'date': str(rec.txn_date),
                'narration': p.get('narration', ''),
                'debit': p.get('debit', 0),
                'credit': p.get('credit', 0),
                'ref_no': p.get('ref_no', ''),
            })

    return ok({
        'unreconciled': unreconciled,
        'total_unreconciled': len(unreconciled),
        'total_debits': sum(t['debit'] for t in unreconciled),
        'total_credits': sum(t['credit'] for t in unreconciled),
    })


@router.post('/transactions/{row_id}/match')
def match_transaction(row_id: str, payload: dict, tenant_id: str = Depends(current_tenant),
                      db: Session = Depends(get_db)):
    """Match a single bank transaction to an invoice/payment."""
    from app.models.e2e import ResourceRecord

    txn_rec = db.query(ResourceRecord).filter_by(
        tenant_id=tenant_id, resource='bank_transaction', resource_id=row_id
    ).first()
    if not txn_rec:
        raise APIError('TRANSACTION_NOT_FOUND', f'Bank transaction {row_id} not found', status_code=404)

    inv_id = payload.get('invoice_id')
    amount = payload.get('amount')

    if not inv_id:
        raise APIError('MISSING_INVOICE', 'invoice_id is required', status_code=400)

    # Quick match using the reconcile endpoint logic
    match_payload = {
        'transaction_id': row_id,
        'matches': [{'invoice_id': inv_id, 'amount': amount or float(txn_rec.payload.get('debit', txn_rec.payload.get('credit', 0))), 'type': 'payment'}]
    }
    result = reconcile_bank_statement(match_payload, tenant_id, db)
    return result