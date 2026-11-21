import base64
import hashlib
import io
import json
import re
from accounting import (
    APPLICATION_KINDS, DOCUMENTS, KINDS, NUMBERED_KINDS, POSTED_KINDS, applied_total, audit,
    bank_account_for, calculate, company_for, company_obj, current_user, db, lock_company,
    master_name_matches, money, next_document_number, obj, posting_account, posting_lines,
    require_open_period, system_account, validate_pos_payment, value_stock_lines,
)
from advance_tax import prepare as prepare_advance_tax, release as release_advance_tax
from datetime import date as DateType, datetime, timezone
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from gst_identifiers import require_gstin
from inventory_setup import EXTRA_KEYS, clean_item_extras
from invoice_requirements import validate_outward_invoice_fields
from models import (
    Company, CompanyPreference, CompanyTaxProfile, DocumentConversion, IdempotencyKey, Journal,
    JournalLine, PaymentAllocation, PaymentSplitAllocation, Record, RecordPosting, StockMovement,
    User,
)
from pydantic import ValidationError
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from schemas import MasterRow, RecordInput, validate_item_image, validate_master_defaults
from sqlalchemy import JSON, Text, case, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from workflow_extensions import available_credit


router = APIRouter()


def compact_record_data(dialect):
    """Trim heavy snapshots in SQL, before database transfer/JSON deserialization."""
    masters = Record.kind.in_(['item', 'party'])
    if dialect == 'postgresql':
        from sqlalchemy.dialects.postgresql import JSONB, ARRAY
        data = cast(Record.data, JSONB)
        for key in ('vyapar_source', 'image_data_url', 'company_snapshot', 'document_branding'):
            data = data.op('-')(key)
        return case((masters, data), else_=func.jsonb_set(data, cast(['lines'], ARRAY(Text)), cast([], JSONB)))
    if dialect == 'sqlite':
        data = func.json_remove(Record.data, '$.vyapar_source', '$.image_data_url',
            '$.company_snapshot', '$.document_branding', type_=JSON)
        return case((masters, data), else_=func.json_set(data, '$.lines', func.json('[]'), type_=JSON))
    return Record.data


@router.get('/api/companies/{company_id}/records')
def records(company_id: str, kind: str = '', compact:bool=False, offset:int=Query(default=0,ge=0),limit:int|None=Query(default=None,ge=1,le=500),user: User = Depends(current_user), session: Session = Depends(db)):
    company_for(company_id, user, session)
    projected = compact and session.bind.dialect.name in {'postgresql', 'sqlite'}
    q = select(Record.id, Record.kind, Record.name, Record.number, Record.date, Record.amount,
        compact_record_data(session.bind.dialect.name).label('data')) if projected else select(Record)
    q = q.where(Record.company_id == company_id, Record.kind.not_in(['vyapar_backup_archive','document_branding','restore_marker','recurring_template','pos_register_session','pos_register_movement','inventory_setup']))
    if kind:q=q.where(Record.kind==kind)
    created_at = func.coalesce(Record.data['created_at'].as_string(), '')
    q=q.order_by(Record.date.desc(),created_at.desc(),Record.id.desc()).offset(offset)
    if limit:q=q.limit(limit)
    if projected:
        from types import SimpleNamespace
        rows=[SimpleNamespace(**row) for row in session.execute(q).mappings()]
    else:rows=list(session.scalars(q))
    if not rows:return []
    page_ids=[row.id for row in rows]
    posted=set(session.scalars(select(RecordPosting.record_id).where(RecordPosting.company_id==company_id,RecordPosting.record_id.in_(page_ids))))
    draft_ids=[row.id for row in rows if row.kind in DOCUMENTS-POSTED_KINDS]
    conversions=dict(session.execute(select(DocumentConversion.source_record_id,DocumentConversion.target_record_id).where(
        DocumentConversion.company_id==company_id,DocumentConversion.source_record_id.in_(draft_ids))).all()) if draft_ids else {}
    consumed={};credit_used={};applied={}
    document_ids=[row.id for row in rows if row.kind in {'sales_invoice','purchase_bill','opening_receivable','opening_payable'} and row.id in posted]
    if document_ids:
        for model in (PaymentAllocation,PaymentSplitAllocation):
            for did,value in session.execute(select(model.document_id,func.sum(model.amount)).where(
                model.company_id==company_id,model.document_id.in_(document_ids)).group_by(model.document_id)):
                applied[did]=applied.get(did,Decimal('0'))+value
    balance_ids=[row.id for row in rows if row.id in posted and (row.data.get('is_advance') or row.kind in {'credit_note','debit_note'})]
    if balance_ids:
        advance_id=Record.data['advance_id'].as_string();note_id=Record.data['credit_note_id'].as_string()
        posted_ids=select(RecordPosting.record_id).where(RecordPosting.company_id==company_id)
        settlements=session.execute(select(advance_id,note_id,func.sum(Record.amount)).where(
            Record.company_id==company_id,Record.id.in_(posted_ids),
            Record.kind.in_(['advance_application','advance_refund','credit_application','customer_refund','supplier_refund']),
            or_(advance_id.in_(balance_ids),note_id.in_(balance_ids))).group_by(advance_id,note_id))
        for source_id,credit_id,amount in settlements:
            if source_id:consumed[source_id]=consumed.get(source_id,Decimal('0'))+amount
            if credit_id:credit_used[credit_id]=credit_used.get(credit_id,Decimal('0'))+amount
    result=[]
    for row in rows:
        value=obj(row)
        if compact and not projected:
            data={k:v for k,v in row.data.items() if k not in {'vyapar_source','image_data_url','company_snapshot','document_branding'}}
            if row.kind not in {'item','party'}:data['lines']=[]
            if isinstance(data.get('document_branding'),dict):data['document_branding']={k:v for k,v in data['document_branding'].items() if k not in {'logo','signature'}}
            value['data']=data
        result.append({**value, **record_status(row, row.id in posted,
            applied=applied.get(row.id, Decimal('0')), consumed=consumed.get(row.id, Decimal('0')),
            credit_used=credit_used.get(row.id, Decimal('0')), converted_to=conversions.get(row.id))})
    return result


def record_status(row, posted, *, applied=Decimal('0'), consumed=Decimal('0'), credit_used=Decimal('0'), converted_to=None):
    """Identical fresh lifecycle fields for compact lists and full detail clients."""
    stock_status = {'stock_posted': True} if row.kind == 'stock_adjustment' and row.data.get('quantity_only') is True else {}
    return {'posted': posted, 'cancelled': bool(row.data.get('cancelled')), **stock_status,
        'advance_remaining': str(row.amount-consumed) if row.data.get('is_advance') and posted else None,
        'credit_remaining': str(Decimal(str(row.data.get('unallocated_credit',0)))-credit_used) if row.kind in {'credit_note','debit_note'} and posted else None,
        'converted_to': converted_to or ('source-converted' if row.data.get('vyapar_converted') else None),
        'outstanding': str(row.amount-applied) if row.kind in {'sales_invoice','purchase_bill','opening_receivable','opening_payable'} and posted else None}


@router.get('/api/companies/{company_id}/records/{record_id}')
def get_record(company_id:str,record_id:str,user:User=Depends(current_user),session:Session=Depends(db)):
    import book_services as services
    company_for(company_id,user,session)
    row=session.scalar(select(Record).where(Record.company_id==company_id,Record.id==record_id,Record.kind.not_in(['vyapar_backup_archive','restore_marker','document_branding','recurring_template','pos_register_session','pos_register_movement','inventory_setup'])))
    if not row:raise HTTPException(404,'Record not found')
    allocations=[]
    for model in (PaymentAllocation,PaymentSplitAllocation):allocations += [{'document_id':r.document_id,'amount':str(r.amount)} for r in session.scalars(select(model).where(model.company_id==company_id,model.payment_id==row.id))]
    posted_ids = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
    posted = bool(session.scalar(select(RecordPosting.id).where(RecordPosting.company_id==company_id,RecordPosting.record_id==row.id)))
    settlements = list(session.scalars(select(Record).where(Record.company_id==company_id, Record.id.in_(posted_ids),
        Record.kind.in_(['advance_application','advance_refund','credit_application','customer_refund','supplier_refund']),
        or_(Record.data['advance_id'].as_string()==row.id, Record.data['credit_note_id'].as_string()==row.id))))
    consumed = sum((r.amount for r in settlements if r.data.get('advance_id')==row.id), Decimal('0'))
    credit_used = sum((r.amount for r in settlements if r.data.get('credit_note_id')==row.id), Decimal('0'))
    converted_to = session.scalar(select(DocumentConversion.target_record_id).where(DocumentConversion.company_id==company_id, DocumentConversion.source_record_id==row.id))
    capacity = None
    if row.kind in {'purchase_bill','sales_invoice','pos'}:
        from purchase_returns import remaining_source_lines
        capacity = remaining_source_lines(services, row, session)
    serialized = obj(row)
    if row.kind == 'customer_refund':
        from cancellation import pos_refund_cancellable
        serialized['pos_refund_cancellable'] = posted and pos_refund_cancellable(services, row, session)
    if capacity is not None:
        serialized['return_capacity_lines'] = capacity
        if row.kind == 'purchase_bill': serialized['data'] = {**serialized['data'], 'lines': capacity}
    from record_trail import document_trail
    trail = document_trail(services, session, company_id, row)
    return {**serialized, **record_status(row, posted, applied=applied_total(company_id,row.id,session),
        consumed=consumed, credit_used=credit_used, converted_to=converted_to), 'allocations':allocations, 'document_trail':trail}


@router.post('/api/companies/{company_id}/advances/{advance_id}/apply')
def apply_advance(company_id: str, advance_id: str, body: RecordInput, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    return apply_advance_in_transaction(company_id, advance_id, body, request, user, session)


def apply_advance_in_transaction(company_id, advance_id, body, request, user, session, *, commit=True):
    import book_services as services
    lock_company(company_id, user, session)
    key = request.headers.get('Idempotency-Key', '').strip()
    if not key or len(key) > 80: raise HTTPException(422, 'A valid idempotency key is required')
    fingerprint = hashlib.sha256(json.dumps({'advance_id': advance_id, 'body': body.model_dump(mode='json')}, sort_keys=True).encode()).hexdigest()
    previous = session.scalar(select(IdempotencyKey).where(IdempotencyKey.company_id == company_id, IdempotencyKey.key == key))
    if previous:
        if previous.request_hash != fingerprint: raise HTTPException(409, 'Idempotency key was used for a different request')
        existing = session.get(Record, previous.record_id)
        posted = session.scalar(select(RecordPosting.id).where(
            RecordPosting.company_id == company_id, RecordPosting.record_id == existing.id))
        return {**obj(existing), 'posted': bool(posted)}
    require_open_period(company_id, body.date, session)
    source = session.scalar(select(Record).where(Record.company_id == company_id, Record.id == advance_id))
    if not source or source.kind not in {'payment_in', 'payment_out'} or not source.data.get('is_advance'):
        raise HTTPException(404, 'Advance not found')
    if not session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id, RecordPosting.record_id == source.id)):
        raise HTTPException(422, 'Advance must be posted')
    target_id = body.data.get('applied_to')
    if not isinstance(target_id, str): raise HTTPException(422, 'Choose an invoice or bill')
    target = session.scalar(select(Record).where(Record.company_id == company_id, Record.id == target_id, Record.kind == APPLICATION_KINDS[source.kind]))
    if not target or not session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id, RecordPosting.record_id == target.id)):
        raise HTTPException(422, 'Choose a posted invoice or bill in this company')
    if source.name.strip().casefold() != target.name.strip().casefold(): raise HTTPException(422, 'Party must match the advance')
    if body.date < max(source.date, target.date): raise HTTPException(422, 'Application date cannot precede the advance or document')
    amount = money(body.amount)
    from advance_tax import active_settlements
    used = sum((r.amount for r in active_settlements(services, company_id, session, source_ids=[source.id])), Decimal('0'))
    if amount <= 0 or amount > source.amount - used: raise HTTPException(422, 'Amount exceeds the available advance')
    if amount > target.amount - applied_total(company_id, target.id, session): raise HTTPException(422, 'Amount exceeds the outstanding document balance')
    advance_base,advance_taxes,advance_data=release_advance_tax(services,company_id,source,amount,used,session,target)
    application = Record(company_id=company_id, kind='advance_application', name=source.name, date=body.date, amount=amount,
        data={**advance_data,'applied_to':target.id,'created_at':datetime.now(timezone.utc).isoformat()})
    session.add(application); session.flush()
    application.number = 'ADV-' + application.id[:8].upper()
    journal = Journal(company_id=company_id, date=body.date, reference='AUTO:' + application.id, memo='Advance application ' + application.number, created_by=user.id)
    session.add(journal); session.flush()
    debit, credit = ('customer_advances', 'receivable') if source.kind == 'payment_in' else ('payable', 'supplier_advances')
    debit_value=advance_base if source.kind=='payment_in' else amount
    if debit_value:session.add(JournalLine(company_id=company_id,journal_id=journal.id,account_id=system_account(company_id,debit,session),debit=debit_value,credit=Decimal('0')))
    session.add_all([
        JournalLine(company_id=company_id, journal_id=journal.id, account_id=system_account(company_id, credit, session), debit=Decimal('0'), credit=amount),
        RecordPosting(company_id=company_id, record_id=application.id, journal_id=journal.id),
        PaymentSplitAllocation(company_id=company_id, payment_id=application.id, document_id=target.id, amount=amount),
        IdempotencyKey(company_id=company_id, key=key, request_hash=fingerprint, record_id=application.id)])
    for tax_key,tax_value in advance_taxes.items():
        if tax_value:session.add(JournalLine(company_id=company_id,journal_id=journal.id,account_id=system_account(company_id,'output_'+tax_key,session),debit=tax_value,credit=Decimal('0')))
    audit(session, company_id, user, 'advance.applied', 'advance_application', application.id, {'advance_id': source.id, 'document_id': target.id, 'amount': str(amount)})
    if commit: session.commit()
    else: session.flush()
    return {**obj(application), 'posted': True}


def resolve_party(company_id, name, session):
    matches = master_name_matches(company_id, 'party', name, session)
    if len(matches) > 1:
        raise HTTPException(409, 'Ambiguous legacy party names require review before continuing; no parties were merged')
    return matches[0] if matches else None


def validate_active_references(company_id, kind, name, data, session, historical_record=None):
    """Archive prevents new business, not correction or settlement of existing debt.

    Exceptions come only from server-loaded source records, never client flags.
    Conversions deliberately do not inherit an inactive-master exception.
    """
    allowed_party=set();allowed_items=set()
    def retain(source):
        if source and source.company_id==company_id:
            allowed_party.add(source.data.get('party_id') or source.name.strip().casefold())
            allowed_items.update(line.get('item_id') or str(line.get('description','')).strip().casefold() for line in source.data.get('lines',[]) if isinstance(line,dict))
    retain(historical_record)
    if kind in {'credit_note','debit_note'} and isinstance(data.get('applied_to'),str) and data.get('applied_to'):
        target=session.get(Record,data['applied_to'])
        if target and target.kind in ({'sales_invoice','pos'} if kind=='credit_note' else {'purchase_bill'}):retain(target)
    if kind in {'payment_in','payment_out'} and not data.get('is_advance'):
        ids=[data['applied_to']] if data.get('applied_to') else []
        allocations=data.get('allocations')
        if isinstance(allocations,list):ids += [r.get('document_id') for r in allocations if isinstance(r,dict)]
        for rid in ids:
            if not isinstance(rid,str):continue
            target=session.get(Record,rid)
            if target and target.kind in ({'sales_invoice','opening_receivable'} if kind=='payment_in' else {'purchase_bill','opening_payable'}):retain(target)
    party=resolve_party(company_id, name, session)
    if data.get('party_id') and (not party or party.id!=data['party_id']):
        raise HTTPException(422,'Party identity does not match this company and name')
    if party and party.data.get('is_active',True) is False and party.id not in allowed_party and party.name.strip().casefold() not in allowed_party:
        raise HTTPException(422,'Reactivate this party before creating a new document')
    lines=data.get('lines',[])
    if not isinstance(lines,list):return # normal document validation provides the shape error
    identities=set();names=set()
    for line in lines:
        if not isinstance(line,dict):continue
        iid=line.get('item_id')
        if isinstance(iid,str) and iid:identities.add(iid)
        else:names.add(str(line.get('description','')).strip().casefold())
    if identities or names:
        candidates=[item for item in session.scalars(select(Record).where(Record.company_id==company_id,Record.kind=='item')) if item.id in identities or item.name.strip().casefold() in names]
        for item in candidates:
            if item.data.get('is_active',True) is False and item.id not in allowed_items and item.name.strip().casefold() not in allowed_items:
                raise HTTPException(422,'Reactivate this item before adding it to a new document')


@router.post('/api/companies/{company_id}/records')
def create_record(company_id: str, body: RecordInput, request: Request, user: User = Depends(current_user), session: Session = Depends(db)):
    body = body.model_copy(update={'data': client_record_data(body.data)})
    return save_record(company_id, body, request, user, session)


def client_record_data(data):
    """Keep lifecycle and integration ownership on the server at HTTP boundaries.

    Internal posting callers can still attach verified commerce/import lineage.
    Draft/edit version checks read the submitted version before using this helper.
    """
    reserved = {'cancelled', 'version', 'created_at', 'updated_at', 'editing_record_id',
                'recurring_template_id', 'recurring_occurrence_date', 'unallocated_credit',
                'outstanding', 'advance_remaining', 'credit_remaining', 'posted',
                'company_snapshot', 'document_branding', 'advance_tax', 'advance_taxable',
                'advance_tax_event', 'advance_tax_released', 'payment_kind', 'advance_id', 'credit_id',
                'pos_return', 'pos_register_session_id', 'quantity_only'}
    from purchase_receiving import OWNED_FIELDS
    return {key: value for key, value in data.items()
            if key not in reserved and key not in OWNED_FIELDS and not key.startswith(('vyapar_', 'commerce_', 'receipt_correction'))}


def validate_outward_document_number(kind, tax_mode, number):
    # GST tax invoices, bills of supply and outward credit notes use an
    # alphanumeric serial, with slash/hyphen as the only special characters.
    # Supplier references and historical reads retain their existing formats.
    if tax_mode in {'regular', 'composition'} and kind in {'sales_invoice', 'pos', 'credit_note'}:
        if not re.fullmatch(r'[A-Za-z0-9/-]{1,16}', number):
            raise HTTPException(422, 'GST document number must contain 1–16 letters, digits, / or - only')


def save_record(company_id, body, request, user, session, *, commit=True, historical_record=None, idempotency_request_hash=None,
                calculated_pos_return=None):
    from routers.companies import branding_for
    import book_services as services
    """Post inside the caller transaction when processing a durable integration event."""
    company = lock_company(company_id, user, session)
    if body.kind not in KINDS: raise HTTPException(422, 'Unsupported record type')
    idempotency_key = request.headers.get('Idempotency-Key', '').strip()
    if len(idempotency_key) > 80: raise HTTPException(422, 'Idempotency key is too long')
    request_hash = idempotency_request_hash or hashlib.sha256(json.dumps(body.model_dump(mode='json'), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if idempotency_key:
        previous = session.scalar(select(IdempotencyKey).where(IdempotencyKey.company_id == company_id, IdempotencyKey.key == idempotency_key))
        if previous:
            if previous.request_hash != request_hash: raise HTTPException(409, 'Idempotency key was used for a different request')
            existing = session.get(Record, previous.record_id)
            return {**obj(existing), 'posted': bool(session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id, RecordPosting.record_id == existing.id)))}
    data, amount = {k:v for k,v in body.data.items() if k not in {'recurring_template_id','recurring_occurrence_date'}}, money(body.amount)
    data.pop('unallocated_credit', None)
    if body.kind not in {'credit_note', 'debit_note'}:
        # Only a return note can opt out of physical stock movement. Ordinary
        # purchases/sales must keep their stock quantity and inventory journals aligned.
        data.pop('return_stock', None)
    elif 'return_stock' in data and not isinstance(data['return_stock'], bool):
        raise HTTPException(422, 'Choose whether this return includes stock')
    if body.kind in DOCUMENTS|POSTED_KINDS:
        validate_active_references(company_id, body.kind, body.name, data, session, historical_record)
    if body.kind in {'payment_in','payment_out','bank_transfer'}:
        data={k:v for k,v in data.items() if k not in {'advance_tax','advance_tax_released','advance_tax_event','advance_taxable','lines','cgst','sgst','igst','taxable','taxable_supply_value','tax_mode','pending_input_cgst','pending_input_sgst','pending_input_igst','round_off'}}
        data.update(cgst='0',sgst='0',igst='0',lines=[],round_off='0',advance_tax_event=False)
    if body.kind in DOCUMENTS|POSTED_KINDS:
        party=resolve_party(company_id, body.name, session)
        if data.get('party_id') and (not party or data['party_id']!=party.id):raise HTTPException(422,'Party identity does not match this company and name')
        if party:
            if body.kind in {'sales_invoice','pos','estimate','proforma','sales_order'} and 'shipping_address' not in data:
                data={**data,'shipping_address':party.data.get('shipping_address','')}
            body.name=party.name;data={**{key:party.data.get(source,'') for key,source in [('party_address','address'),('party_gstin','gstin'),('party_phone','phone')]},**data,'party_id':party.id}
    if body.kind in {'sales_invoice', 'purchase_bill'} and data.get('due_date') not in (None, ''):
        try:
            raw_due = data['due_date']
            if not isinstance(raw_due, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw_due): raise ValueError()
            due = DateType.fromisoformat(raw_due)
        except ValueError:
            raise HTTPException(422, 'Enter a valid due date in YYYY-MM-DD format')
        if due < body.date: raise HTTPException(422, 'Due date cannot be before the document date')
    if body.kind in {'party', 'item'}:
        try: master = MasterRow.model_validate({**data, 'name': body.name})
        except ValidationError: raise HTTPException(422, 'Invalid party or item details')
        validate_item_image(master)
        validate_master_defaults(master, body.kind)
        sent_extras = {k: v for k, v in master.model_dump(mode='json').items() if k in EXTRA_KEYS and k in master.model_fields_set}
        extras = clean_item_extras(services, company_id, body.kind, sent_extras, None, session)
        if not master.name.strip(): raise HTTPException(422, 'Name is required')
        if master_name_matches(company_id, body.kind, master.name, session):
            raise HTTPException(409, 'A party or item with this name already exists')
        if body.kind == 'party':
            if master.party_type not in {'customer', 'supplier', 'both'}: raise HTTPException(422, 'Party type must be customer, supplier or both')
            require_gstin(master.gstin, 'Party GSTIN')
            if master.email.strip() and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', master.email.strip()): raise HTTPException(422, 'Enter a valid email')
            data = {'party_type': master.party_type, 'gstin': master.gstin.strip().upper(), 'address': master.address, 'phone': master.phone.strip(), 'email': master.email.strip(), 'payment_terms_days': master.payment_terms_days, 'credit_limit':str(master.credit_limit) if master.credit_limit is not None else None, 'is_active':master.is_active, 'shipping_address':master.shipping_address}
        else:
            data = {key: value for key, value in master.model_dump(mode='json').items() if key in {'hsn', 'unit', 'sale_rate', 'purchase_rate', 'gst_rate', 'track_stock','barcode','item_type','tax_treatment','image_data_url','image_thumbnail','low_stock_threshold','is_active'}}
            data = {**data, **extras}
        body.name = master.name.strip()
    profile = session.get(CompanyTaxProfile, company_id)
    tax_mode = profile.mode if profile else 'regular'
    if tax_mode in {'regular','composition'} and body.kind in {'sales_invoice','pos','credit_note'} and not company.gstin:raise HTTPException(422,'Add the company GSTIN in Settings before issuing registered documents')
    if body.kind in DOCUMENTS and (body.kind != 'expense' or data.get('lines')):
        if calculated_pos_return is not None:
            calculated_fields, amount = calculated_pos_return
            data.update(calculated_fields)
        else:
            data, amount = calculate(data, company, tax_mode, body.kind, session)
        validate_outward_invoice_fields(body.kind, tax_mode, data, body.date)
        data = {**data, 'company_snapshot': company_obj(company, session), 'document_branding': branding_for(company_id, session)}
    if body.kind == 'expense' and not data.get('lines'):
        # Amount-only expenses have no reviewed supplier-tax lines. Ignore stale
        # or forged calculated fields rather than posting unsupported input tax.
        data = {**data, **{key: '0' for key in ('cgst', 'sgst', 'igst', 'supplier_tax',
            'pending_input_cgst', 'pending_input_sgst', 'pending_input_igst',
            'input_tax_ineligible', 'round_off')}, 'lines': [], 'taxable': str(amount)}
    if body.kind == 'pos':
        from pos_validation import payment_amount, requote_required, validate_checkout_date
        if 'expected_total' in data:
            expected = payment_amount(data.pop('expected_total'), 'Enter a valid checkout total')
            if expected != amount:
                raise requote_required('Checkout total changed. Review the updated total before charging.')
        data = validate_pos_payment(company_id, data, amount, session)
        validate_checkout_date(data, body.date)
        from pos_register import tag_posting
        tag_posting(services, company_id, data, session, historical_record)
    if not amount.is_finite() or amount < 0: raise HTTPException(422, 'Amount must be finite and nonnegative')
    if body.kind in POSTED_KINDS:
        require_open_period(company_id, body.date, session)
        if not body.name.strip(): raise HTTPException(422, 'Party or description is required')
        if amount <= 0: raise HTTPException(422, 'Posted transaction amount must be greater than zero')
        if body.kind != 'pos':
            if data.get('payment_account', 'cash') not in ('cash', 'bank'): raise HTTPException(422, 'Payment account must be cash or bank')
            if body.kind == 'bank_transfer' or data.get('payment_account') == 'bank':
                bank_account_for(company_id, data.get('bank_account_id', 'default'), session)
            elif data.get('bank_account_id') not in (None, '', 'default'):
                raise HTTPException(422, 'Bank account can only be selected for bank payments')
    number = body.number.strip()
    if body.kind in NUMBERED_KINDS:
        if not number: number = next_document_number(company_id, body.kind, body.date, session)
        if len(number) > 16: raise HTTPException(422, 'Document number cannot exceed 16 characters')
    validate_outward_document_number(body.kind, tax_mode, number)
    if number and session.scalar(select(Record).where(Record.company_id == company_id, Record.kind == body.kind, Record.number == number)): raise HTTPException(409, 'Document number already exists')
    conversion_source = None
    source_id = data.get('source_document_id')
    if source_id:
        if not isinstance(source_id, str): raise HTTPException(422, 'Invalid source document')
        allowed_sources = {'sales_invoice': {'estimate', 'proforma', 'sales_order'}, 'sales_order': {'estimate', 'proforma'}, 'purchase_bill': {'purchase_order'}}
        if body.kind not in allowed_sources: raise HTTPException(422, 'This document type cannot be converted')
        conversion_source = session.scalar(select(Record).where(Record.company_id == company_id, Record.id == source_id, Record.kind.in_(allowed_sources[body.kind])))
        if not conversion_source: raise HTTPException(422, 'Choose a matching source document in this company')
        if conversion_source.name.strip().casefold() != body.name.strip().casefold(): raise HTTPException(422, 'Conversion party must match the source document')
        if body.date < conversion_source.date: raise HTTPException(422, 'Conversion date cannot precede its source document')
        if conversion_source.data.get('vyapar_converted'): raise HTTPException(409, 'This source document was already converted in Vyapar')
        if conversion_source.kind == 'purchase_order' and conversion_source.data.get('purchase_order_receiving_started'):
            raise HTTPException(409, 'This purchase order has receipts. Post deliveries through the receiving workflow')
        if session.scalar(select(DocumentConversion.id).where(DocumentConversion.company_id == company_id, DocumentConversion.source_record_id == source_id)):
            raise HTTPException(409, 'Source document has already been converted')
    target = None
    allocations = []
    unallocated_receipt = body.kind == 'payment_in' and data.get('receipt_purpose') == 'unallocated'
    if 'receipt_purpose' in data and not unallocated_receipt:
        raise HTTPException(422, 'Invalid receipt purpose')
    if unallocated_receipt:
        if data.get('is_advance') or data.get('allocations') or data.get('applied_to'):
            raise HTTPException(422, 'An unallocated receipt cannot have an advance or invoice allocation')
        for key in ('advance_supply', 'advance_gst_rate', 'place_of_supply'):
            data.pop(key, None)
    if 'utr' in data and body.kind == 'payment_in':
        if not isinstance(data['utr'], str) or len(data['utr'].strip()) > 120:
            raise HTTPException(422, 'Enter a bank UTR of at most 120 characters')
        data['utr'] = data['utr'].strip()
    if data.get('is_advance'):
        if data['is_advance'] is not True or body.kind not in {'payment_in', 'payment_out'}:
            raise HTTPException(422, 'Advance is supported only for receipts and payouts')
        data=prepare_advance_tax(services,data,company,tax_mode,body.kind,amount)
        if data.get('allocations') or data.get('applied_to'): raise HTTPException(422, 'An advance cannot have invoice allocations at creation')
    if body.kind in {'credit_note', 'debit_note'}:
        target = session.scalar(select(Record).where(Record.company_id == company_id, Record.id == data.get('applied_to'), Record.kind.in_(['sales_invoice','pos'] if body.kind=='credit_note' else ['purchase_bill'])))
        if not target or not session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id, RecordPosting.record_id == target.id)):
            raise HTTPException(422, 'Choose a posted source invoice or bill in this company')
        if target.name.strip().casefold() != body.name.strip().casefold(): raise HTTPException(422, 'Party must match the source document')
        if body.date < target.date: raise HTTPException(422, 'Note date cannot precede its source document')
        posted_notes = select(RecordPosting.record_id).where(RecordPosting.company_id == company_id)
        previous_notes = list(session.scalars(select(Record).where(
            Record.company_id == company_id, Record.kind == body.kind, Record.id.in_(posted_notes))))
        previous_notes = [note for note in previous_notes if note.data.get('applied_to') == target.id]
        if body.kind == 'debit_note':
            from purchase_returns import validate_capacity
            validate_capacity(services, target, data, previous_notes)
        elif target.kind == 'pos':
            from purchase_returns import validate_capacity
            validate_capacity(services, target, data, previous_notes, source_label='POS sale')
        if amount + sum((note.amount for note in previous_notes), Decimal('0')) > target.amount:
            raise HTTPException(422, 'Notes exceed the original document amount')
        for tax_key in ('cgst', 'sgst', 'igst', 'supplier_tax', 'pending_input_cgst', 'pending_input_sgst', 'pending_input_igst', 'input_tax_ineligible'):
            reversed_tax = sum((Decimal(str(note.data.get(tax_key, 0))) for note in previous_notes), Decimal('0'))
            if Decimal(str(data.get(tax_key, 0))) + reversed_tax > Decimal(str(target.data.get(tax_key, 0))):
                raise HTTPException(422, 'Note tax exceeds the original document tax')
        for allocation_model in (PaymentAllocation, PaymentSplitAllocation):
            future = session.scalar(select(allocation_model.id).join(Record, Record.id == allocation_model.payment_id).where(
                allocation_model.company_id == company_id, allocation_model.document_id == target.id,
                Record.company_id == company_id, Record.date > body.date).limit(1))
            if future:
                raise HTTPException(409, 'Note date cannot precede an existing settlement; use a date on or after the latest allocation')
        settled = applied_total(company_id, target.id, session)
        offset = min(amount, max(Decimal('0'), target.amount - settled)) if target.kind!='pos' else Decimal('0')
        data = {**data, 'unallocated_credit': str(amount-offset)}
        if offset: allocations.append((target, offset))
    elif body.kind in APPLICATION_KINDS and not data.get('is_advance') and not unallocated_receipt:
        requested = data.get('allocations') if body.kind in {'payment_in', 'payment_out'} else None
        if requested is None: requested = [{'document_id': data.get('applied_to'), 'amount': str(amount)}]
        if not isinstance(requested, list) or not 1 <= len(requested) <= 100:
            raise HTTPException(422, 'Choose one or more invoices or bills')
        seen = set()
        for allocation in requested:
            if not isinstance(allocation, dict): raise HTTPException(422, 'Invalid payment allocation')
            target_id = allocation.get('document_id')
            if not isinstance(target_id, str) or target_id in seen: raise HTTPException(422, 'Each document must be selected once')
            seen.add(target_id)
            try:
                allocated = Decimal(str(allocation.get('amount')))
                if not allocated.is_finite() or allocated <= 0 or allocated > Decimal('9999999999999.99') or allocated.as_tuple().exponent < -2: raise ValueError()
            except (InvalidOperation, ValueError): raise HTTPException(422, 'Enter a positive allocation with at most two decimal places')
            allowed_targets = [APPLICATION_KINDS[body.kind], 'opening_receivable' if body.kind == 'payment_in' else 'opening_payable']
            selected = session.scalar(select(Record).where(Record.company_id == company_id, Record.id == target_id, Record.kind.in_(allowed_targets)))
            if not selected or not session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id, RecordPosting.record_id == selected.id)):
                raise HTTPException(422, 'Choose a posted invoice or bill in this company')
            if selected.name.strip().casefold() != body.name.strip().casefold(): raise HTTPException(422, 'Party must match every selected invoice or bill')
            if body.date < selected.date: raise HTTPException(422, 'Payment or note date cannot be before the linked invoice or bill date')
            if applied_total(company_id, selected.id, session) + allocated > selected.amount:
                raise HTTPException(422, 'Amount exceeds the outstanding document balance')
            allocations.append((selected, allocated))
        if sum((value for _, value in allocations), Decimal('0')) != amount:
            raise HTTPException(422, 'Allocation amounts must equal the payment amount')
        target = allocations[0][0]
    if body.kind in {'purchase_bill', 'debit_note', 'sales_invoice', 'pos', 'credit_note'}:
        data = value_stock_lines(company_id, body.kind, data, tax_mode, body.date, target, session)
    if body.kind in POSTED_KINDS:data={**data,'company_snapshot':company_obj(company,session),'document_branding':branding_for(company_id,session)}
    data={**data,'created_at':datetime.now(timezone.utc).isoformat()}
    r = Record(company_id=company_id, kind=body.kind, name=body.name, number=number, date=body.date, amount=amount, data=data)
    session.add(r)
    try:
        session.flush()
        if body.kind in POSTED_KINDS:
            journal = Journal(company_id=company_id, date=body.date, reference='AUTO:' + r.id, memo=f'{body.kind} {body.number or r.id}', created_by=user.id)
            session.add(journal); session.flush()
            for key, debit, credit in posting_lines(body.kind, amount, data, tax_mode):
                session.add(JournalLine(company_id=company_id, journal_id=journal.id, account_id=posting_account(company_id, key, session), debit=debit, credit=credit))
            session.add(RecordPosting(company_id=company_id, record_id=r.id, journal_id=journal.id))
            if body.kind in {'purchase_bill', 'debit_note', 'sales_invoice', 'pos', 'credit_note'} and data.get('return_stock') is not False:
                for index, line in enumerate(data.get('lines', [])):
                    item_id = line.get('item_id')
                    if not item_id: continue
                    item = session.get(Record, item_id)
                    if not item.data.get('track_stock'): continue
                    quantity = Decimal(str(line['quantity'])) * (1 if body.kind in {'purchase_bill', 'credit_note'} else -1)
                    cost_value = Decimal(str(line['inventory_cost'])) * (1 if quantity > 0 else -1)
                    session.add(StockMovement(company_id=company_id, item_id=item_id, source_record_id=r.id,
                                              line_index=index, date=body.date, quantity=quantity, cost_value=cost_value))
                session.flush()
                # Billing may take quantities below zero. value_stock_lines
                # enforces chronology, source returns and reservation checks.
            for selected, allocated in allocations:
                allocation_class = PaymentSplitAllocation if body.kind in {'payment_in', 'payment_out'} else PaymentAllocation
                session.add(allocation_class(company_id=company_id, payment_id=r.id, document_id=selected.id, amount=allocated))
        if conversion_source:
            session.add(DocumentConversion(company_id=company_id, source_record_id=conversion_source.id, target_record_id=r.id))
        if idempotency_key:
            session.add(IdempotencyKey(company_id=company_id, key=idempotency_key, request_hash=request_hash, record_id=r.id))
        audit(session, company_id, user, 'record.posted' if body.kind in POSTED_KINDS else 'record.created', body.kind, r.id, {'number': number, 'amount': str(amount)})
        if hasattr(services, 'commerce_stock_changed'):
            services.commerce_stock_changed(company_id, session)
        if commit: session.commit()
        else: session.flush()
    except IntegrityError:
        session.rollback()
        if idempotency_key:
            # A concurrent request with the same key won the race: return its result.
            winner = session.scalar(select(IdempotencyKey).where(IdempotencyKey.company_id == company_id, IdempotencyKey.key == idempotency_key))
            if winner and winner.request_hash == request_hash:
                existing = session.get(Record, winner.record_id)
                return {**obj(existing), 'posted': bool(session.scalar(select(RecordPosting.id).where(RecordPosting.company_id == company_id, RecordPosting.record_id == existing.id)))}
        raise HTTPException(409, 'Transaction conflicts with an existing record')
    session.refresh(r)
    return {**obj(r), 'posted': body.kind in POSTED_KINDS}


@router.get('/api/companies/{company_id}/documents/{record_id}.pdf')
def document_pdf(company_id: str, record_id: str, template: str = '', user: User = Depends(current_user), session: Session = Depends(db)):
    from routers.companies import branding_for, with_payment_details
    import book_services as services
    company_for(company_id, user, session)
    record = session.scalar(select(Record).where(Record.company_id == company_id, Record.id == record_id, Record.kind.in_(DOCUMENTS|{'payment_in','payment_out','customer_refund','supplier_refund','advance_refund'})))
    if not record: raise HTTPException(404, 'Document not found')
    if record.data.get('cancelled'):
        raise HTTPException(409, 'Cancelled documents cannot be exported as active originals; review the retained document and cancellation audit history')
    from types import SimpleNamespace
    from currency import format_inr
    current_brand=branding_for(company_id,session);document_data=dict(record.data)
    # Resolve PDF traceability from this tenant's stored source, never submitted display metadata.
    source_reference = ''
    if record.kind in {'credit_note', 'debit_note'}:
        source_id = document_data.get('applied_to')
        allowed = {'sales_invoice', 'pos'} if record.kind == 'credit_note' else {'purchase_bill'}
        source = session.scalar(select(Record).where(Record.company_id == company_id,
            Record.id == source_id, Record.kind.in_(allowed))) if isinstance(source_id, str) and source_id else None
        if source:
            label = {'sales_invoice': 'Original sales invoice', 'pos': 'Original POS receipt',
                     'purchase_bill': 'Linked purchase bill (book reference)'}[source.kind]
            source_reference = label + ': ' + (source.number or 'Number not recorded') + '\nSource date: ' + source.date.strftime('%d %b %Y')
            if source.data.get('cancelled'):
                source_reference += '\nSource is marked cancelled; review its retained history.'
        else:
            source_reference = 'Original document reference unavailable; review the source records.' if source_id else 'Original document not linked; review the source records.'
        if record.kind == 'debit_note':
            source_reference += '\nPurchase return in these books; not a supplier-issued GST debit note.'
    if record.kind in {'sales_invoice', 'purchase_bill'}:
        # Settlement also includes credit/debit notes. Show actual payments separately.
        payments = Decimal('0')
        for allocation in (PaymentAllocation, PaymentSplitAllocation):
            query = select(func.coalesce(func.sum(allocation.amount), 0)).join(Record, Record.id == allocation.payment_id).where(
                allocation.company_id == company_id, allocation.document_id == record.id,
                Record.company_id == company_id, Record.kind.in_(['payment_in', 'payment_out', 'advance_application']))
            payments += Decimal(str(session.scalar(query)))
        document_data['payments_applied'] = str(payments)
    if 'logo' in current_brand:document_data['document_branding']={**(document_data.get('document_branding') or {}),'logo':current_brand['logo']}
    if record.kind in {'sales_invoice','pos','estimate','proforma','sales_order','credit_note'}:
        document_data['document_branding']=with_payment_details(company_id,document_data.get('document_branding') or {},current_brand,session)
    record=SimpleNamespace(id=record.id,kind=record.kind,name=record.name,number=record.number,date=record.date,amount=record.amount,data=document_data,source_reference=source_reference)
    voucher=record.kind in {'payment_in','payment_out','customer_refund','supplier_refund','advance_refund'}
    if voucher:
        from types import SimpleNamespace
        data=dict(record.data);taxed=bool(data.get('advance_tax_event'))
        if taxed:
            data={**data,**{key:str(abs(Decimal(str(data.get(key,0))))) for key in ('cgst','sgst','igst','taxable','taxable_supply_value')}}
            if not data.get('taxable') or Decimal(data['taxable'])==0:data['taxable']=str(record.amount-sum(Decimal(data[key]) for key in ('cgst','sgst','igst')))
            data['lines']=[{**line,**{key:str(abs(Decimal(str(line.get(key,0))))) for key in ('rate','taxable','tax')}} for line in data.get('lines',[])]
        else:
            data.update(tax_mode='unregistered',taxable=str(record.amount),cgst='0',sgst='0',igst='0',lines=[{'description':record.kind.replace('_',' ').title(),'quantity':'1','rate':str(record.amount),'taxable':str(record.amount),'tax':'0','gst_rate':'0'}])
        links=list(session.scalars(select(PaymentAllocation).where(PaymentAllocation.company_id==company_id,PaymentAllocation.payment_id==record.id)))+list(session.scalars(select(PaymentSplitAllocation).where(PaymentSplitAllocation.company_id==company_id,PaymentSplitAllocation.payment_id==record.id)))
        references=[]
        for link in links:
            target=session.scalar(select(Record).where(Record.company_id==company_id,Record.id==link.document_id))
            if target:references.append((target.number or target.name)+' · INR '+str(link.amount))
        if references:data['notes']=(str(data.get('notes',''))+chr(10)+'Applied to: '+', '.join(references)).strip()
        if data.get('is_advance'):data['notes']=(str(data.get('notes',''))+chr(10)+'Advance payment; unused amounts remain available for application or refund.').strip()
        record=SimpleNamespace(id=record.id,kind=record.kind,name=record.name,number=record.number,date=record.date,amount=record.amount,data=data)

    palette = {
        'classic': (colors.HexColor('#244f43'), colors.HexColor('#edf4ee'), 8, True),
        'modern': (colors.HexColor('#1a6475'), colors.HexColor('#e7f2f5'), 12, False),
        'compact': (colors.HexColor('#343c45'), colors.HexColor('#f3f4f5'), 5, True),
        'bold': (colors.HexColor('#752f39'), colors.HexColor('#f8ecee'), 13, True),
        'minimal': (colors.HexColor('#343c45'), colors.white, 5, False),
    }
    if not template:
        preference = session.get(CompanyPreference, company_id)
        template = preference.document_template if preference else 'classic'
    from document_fonts import REGULAR_FONT, BOLD_FONT
    from document_layouts import LAYOUTS, THERMAL, render_document, render_thermal, line_discount_label
    if template in LAYOUTS or template in THERMAL:
        data = record.data or {}
        supplier = data.get('company_snapshot') or company_obj(session.get(Company, company_id), session)
        mode = data.get('tax_mode', supplier.get('tax_mode', 'regular'))
        bill = mode == 'composition' or mode == 'regular' and data.get('document_tax_form') == 'bill_of_supply'
        title = {'sales_invoice': 'Bill of Supply' if bill else 'Invoice-cum-Bill of Supply' if data.get('document_tax_form') == 'invoice_cum_bill' else 'Tax Invoice' if mode == 'regular' else 'Invoice', 'purchase_bill': 'Purchase Bill', 'estimate': 'Quotation', 'proforma': 'Proforma Invoice', 'sales_order': 'Sales Order', 'credit_note': 'Credit Note', 'debit_note': 'Debit Note', 'purchase_order': 'Purchase Order', 'expense':'Expense Voucher','payment_in':'Receipt Voucher','payment_out':'Payment Voucher','customer_refund':'Customer Refund Voucher','supplier_refund':'Supplier Refund Receipt','advance_refund':'Advance Refund Voucher', 'pos': 'Bill of Supply Receipt' if bill else 'POS Receipt'}[record.kind]
        paid = applied_total(company_id, record.id, session) if record.kind in {'sales_invoice', 'purchase_bill'} else record.amount if record.kind == 'pos' or voucher else Decimal('0')
        paid = record.amount - available_credit(services,company_id,record,session) if record.kind in {'credit_note','debit_note'} else record.amount if record.kind=='expense' else paid
        branding={**(data.get('document_branding') or {}),**{k:data[k] for k in ('notes','terms') if data.get(k)}}
        if voucher:
            branding={**branding,'upi_id':''}
            bank=bank_account_for(company_id,str(data.get('bank_account_id') or 'default'),session) if data.get('payment_account')=='bank' else None
            if bank:branding.update(bank_name=bank.name,account_number=bank.account_hint,ifsc='',branch='')
            elif data.get('payment_account','cash')=='cash':branding.update(bank_name='',account_number='',ifsc='',branch='')
        result = (render_thermal if template in THERMAL else render_document)(record, supplier, branding, template, title, paid)
        return Response(result, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{record.kind}-{record.id[:8]}.pdf"'})
    if template not in palette: raise HTTPException(404, 'Document layout not found')
    accent, tint, padding, grid = palette[template]
    data = record.data or {}
    supplier = data.get('company_snapshot') or company_obj(session.get(Company, company_id), session)
    tax_mode = data.get('tax_mode', supplier.get('tax_mode', 'regular'))
    def safe(value):
        from html import escape
        return escape(str(value or ''))
    bill_of_supply = tax_mode == 'composition' or tax_mode == 'regular' and data.get('document_tax_form') == 'bill_of_supply'
    title = {'sales_invoice': 'Bill of Supply' if bill_of_supply else 'Invoice-cum-Bill of Supply' if data.get('document_tax_form') == 'invoice_cum_bill' else 'Tax Invoice' if tax_mode == 'regular' else 'Invoice', 'purchase_bill': 'Purchase Bill', 'estimate': 'Estimate', 'proforma': 'Proforma Invoice', 'sales_order': 'Sales Order', 'credit_note': 'Credit Note', 'debit_note': 'Debit Note', 'purchase_order': 'Purchase Order', 'expense':'Expense Voucher','payment_in':'Receipt Voucher','payment_out':'Payment Voucher','customer_refund':'Customer Refund Voucher','supplier_refund':'Supplier Refund Receipt','advance_refund':'Advance Refund Voucher', 'pos': 'Bill of Supply Receipt' if bill_of_supply else 'POS Receipt'}[record.kind]
    out = io.BytesIO()
    pdf = SimpleDocTemplate(out, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40, title=title)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ApexTitle', parent=styles['Title'], fontName=BOLD_FONT, fontSize=20 if template != 'compact' else 15, leading=23, textColor=accent, spaceAfter=10))
    styles.add(ParagraphStyle(name='ApexBody', parent=styles['Normal'], fontName=REGULAR_FONT, fontSize=8 if template == 'minimal' else 9, leading=11 if template == 'minimal' else 13))
    styles.add(ParagraphStyle(name='ApexHead', parent=styles['Normal'], fontName=BOLD_FONT, fontSize=9, leading=13, textColor=colors.white))
    styles.add(ParagraphStyle(name='ApexSmall', parent=styles['Normal'], fontName=REGULAR_FONT, fontSize=8, leading=11, textColor=colors.HexColor('#52605b')))
    styles.add(ParagraphStyle(name='ApexRight', parent=styles['Normal'], fontName=BOLD_FONT, fontSize=10, alignment=TA_RIGHT, textColor=accent))
    elements = [Paragraph(safe(title), styles['ApexTitle'])]
    legacy_branding=data.get('document_branding') or {}
    if legacy_branding.get('logo'):
        from reportlab.platypus import Image as PdfImage
        logo=PdfImage(io.BytesIO(base64.b64decode(legacy_branding['logo'].split(',',1)[1])));logo._restrictSize(95,60);elements.insert(0,logo)
    if tax_mode == 'composition' and record.kind in {'sales_invoice', 'pos'}:
        elements.append(Paragraph('Composition taxable person, not eligible to collect tax on supplies', styles['ApexBody']))
    header = Table([
        [Paragraph('<b>' + safe(supplier.get('name')) + '</b><br/>' + safe(supplier.get('address')) + ('<br/>GSTIN: ' + safe(supplier.get('gstin')) if supplier.get('gstin') else ''), styles['ApexBody']),
         Paragraph('<b>No:</b> ' + safe(record.number or record.id[:8]) + '<br/><b>Date:</b> ' + record.date.isoformat() + ('<br/><b>Due date:</b> ' + safe(data['due_date']) if data.get('due_date') else '') + ('<br/><b>Place of supply:</b> ' + safe(data.get('place_of_supply')) if tax_mode == 'regular' else ''), styles['ApexBody'])],
        [Paragraph('<b>Bill to</b><br/>' + safe(record.name) + '<br/>' + safe(data.get('party_address')) + ('<br/>GSTIN: ' + safe(data.get('party_gstin')) if data.get('party_gstin') else ''), styles['ApexBody']), '']
    ], colWidths=[280, 235])
    header.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), tint), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), padding), ('TOPPADDING', (0, 0), (-1, -1), padding), ('BOTTOMPADDING', (0, 0), (-1, -1), padding)]))
    elements += [header, Spacer(1, 18)]
    if getattr(record, 'source_reference', ''):
        elements += [Paragraph(safe(record.source_reference).replace('\n', '<br/>'), styles['ApexBody']), Spacer(1, 10)]
    has_gst = (tax_mode == 'regular' and not (bill_of_supply and record.kind in {'sales_invoice', 'pos'})) or any(Decimal(str(line.get('tax', 0))) > 0 for line in data.get('lines', []))
    headings = ['Description', 'HSN / SAC', 'Qty', 'Rate', 'Disc.', 'GST', 'Amount'] if has_gst else ['Description', 'HSN / SAC', 'Qty', 'Rate', 'Disc.', 'Amount']
    widths = [155, 55, 35, 60, 42, 65, 103] if has_gst else [190, 65, 45, 70, 50, 95]
    rows = [[Paragraph(safe(h), styles['ApexHead']) for h in headings]]
    for line in data.get('lines', []):
        description = safe(line.get('description'))
        if line.get('details'): description += '<br/><font size="8">' + safe(line['details']).replace('\n', '<br/>') + '</font>'
        if line.get('unit'): description += '<br/>Unit: ' + safe(line['unit'])
        if line.get('price_includes_tax'): description += '<br/>Rate includes GST'
        if Decimal(str(line.get('document_discount', 0))): description += '<br/>Document discount: INR ' + safe(format_inr(line['document_discount']))
        if line.get('tax_treatment') in {'nil_rated', 'exempt', 'non_gst'}:
            description += '<br/><font size="7" color="#52605b">' + {'nil_rated': 'Nil-rated supply', 'exempt': 'Exempt supply', 'non_gst': 'Non-GST supply'}[line['tax_treatment']] + '</font>'
        if tax_mode == 'regular' and record.kind in {'purchase_bill', 'purchase_order', 'debit_note'} and Decimal(str(line.get('tax', 0))) > 0:
            treatment = 'GST included in cost' if line.get('itc_treatment') == 'ineligible' else 'Input credit pending review'
            description += '<br/><font size="7" color="#52605b">' + treatment + '</font>'
        base = [Paragraph(description, styles['ApexBody']), safe(line.get('hsn')), safe(line.get('quantity')), safe(line.get('rate')), Paragraph(safe(line_discount_label(line)), styles['ApexBody'])]
        if has_gst: base.append(safe(line.get('gst_rate')) + '%')
        base.append(safe(Decimal(str(line.get('taxable', 0))) + Decimal(str(line.get('tax', 0)))))
        rows.append(base)
    if len(rows) == 1: rows.append([safe(record.name)] + [''] * (len(headings) - 2) + [safe(record.amount)])
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign='LEFT')
    table_style = [('FONTNAME', (0, 0), (-1, -1), REGULAR_FONT), ('BACKGROUND', (0, 0), (-1, 0), accent), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), padding), ('BOTTOMPADDING', (0, 0), (-1, -1), padding)]
    if grid: table_style.append(('LINEBELOW', (0, 0), (-1, -1), .3, colors.HexColor('#dce4df')))
    table.setStyle(TableStyle(table_style)); elements += [table, Spacer(1, 18)]
    discounted = any(Decimal(str(line.get(key, 0))) for line in data.get('lines', []) for key in ('discount', 'document_discount'))
    totals = [('Subtotal after discounts' if discounted else 'Subtotal', data.get('taxable', record.amount))]
    if has_gst:
        totals += [(key.upper(), data.get(key, '0.00')) for key in ('cgst', 'sgst', 'igst') if Decimal(str(data.get(key, 0))) > 0]
        if Decimal(str(data.get('supplier_tax', 0))) > 0: totals.append(('Supplier tax (unclassified)', data['supplier_tax']))
    if record.kind == 'pos':
        method = data.get('payment_account', 'cash')
        if method == 'split':
            totals.extend([('Paid in cash', data['cash_amount']), ('Bank / UPI / card', data['bank_amount']),
                           ('Cash tendered', data['tender_amount']), ('Change', data['change_amount'])])
        else:
            totals.append(('Paid through', str(method).title()))
    if Decimal(str(data.get('additional_charges', 0))): totals.append(('Additional charges', data['additional_charges']))
    if Decimal(str(data.get('round_off', 0))): totals.append(('Round off', data['round_off']))
    totals.append(('Total (INR)', record.amount))
    total_table = Table([[Paragraph(safe(label), styles['ApexSmall']), Paragraph(safe(value), styles['ApexRight'])] for label, value in totals], colWidths=[385, 130], hAlign='RIGHT')
    total_table.setStyle(TableStyle([('LINEABOVE', (0, -1), (-1, -1), 1, accent), ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    elements += [KeepTogether([total_table]), Spacer(1, 16)]
    # Bank, UPI, notes and signature: the same payment details the reference layouts print.
    brand = {**legacy_branding, **{k: data[k] for k in ('notes', 'terms') if data.get(k)}}
    if voucher: brand = {**brand, 'upi_id': ''}
    bank_lines = [safe(label) + ': ' + safe(brand[key]) for key, label in [('bank_name', 'Bank'), ('account_number', 'Account #'), ('ifsc', 'IFSC'), ('branch', 'Branch')] if brand.get(key)]
    if record.kind in {'sales_invoice', 'purchase_bill'}: legacy_paid = applied_total(company_id, record.id, session)
    elif record.kind in {'credit_note', 'debit_note'}: legacy_paid = record.amount - available_credit(services, company_id, record, session)
    elif record.kind in {'pos', 'expense'} or voucher: legacy_paid = record.amount
    else: legacy_paid = Decimal('0')
    payable = max(Decimal('0'), record.amount - legacy_paid)
    qr_cell = ''
    if brand.get('upi_id') and record.kind in {'sales_invoice', 'estimate', 'proforma', 'pos'} and payable > 0:
        from urllib.parse import urlencode
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics.shapes import Drawing
        code = QrCodeWidget('upi://pay?' + urlencode({'pa': brand['upi_id'], 'pn': supplier.get('name', ''), 'cu': 'INR', 'am': format(payable, '.2f')}))
        x0, y0, x1, y1 = code.getBounds(); side = 78
        drawing = Drawing(side, side, transform=[side / (x1 - x0), 0, 0, side / (y1 - y0), 0, 0]); drawing.add(code)
        qr_cell = [Paragraph('<b>Pay using UPI</b>', styles['ApexBody']), drawing, Paragraph(safe(brand['upi_id']), styles['ApexSmall'])]
    if record.kind in {'sales_invoice', 'purchase_bill'}:
        payments = Decimal(str(data.get('payments_applied', legacy_paid)))
        adjustments = max(Decimal('0'), legacy_paid - payments)
        settlement = [('Payments received' if record.kind == 'sales_invoice' else 'Payments made', payments)]
        if adjustments: settlement.append(('Credit notes / adjustments' if record.kind == 'sales_invoice' else 'Debit notes / adjustments', adjustments))
        settlement.append(('Balance due', payable))
    elif record.kind in {'credit_note', 'debit_note'}:
        settlement = [('Credit used / refunded', legacy_paid), ('Credit remaining', payable)]
    else: settlement = []
    if settlement:
        elements += [Paragraph('<br/>'.join(safe(label) + ': INR ' + safe(format_inr(value)) for label, value in settlement), styles['ApexBody']), Spacer(1, 8)]
    signature_cell = [Paragraph('For ' + safe(supplier.get('name')), styles['ApexBody'])]
    if brand.get('signature'):
        from reportlab.platypus import Image as PdfImage
        try:
            sign = PdfImage(io.BytesIO(base64.b64decode(brand['signature'].split(',', 1)[1]))); sign._restrictSize(95, 50); signature_cell.append(sign)
        except Exception: pass
    signature_cell.append(Paragraph('Authorized signatory', styles['ApexSmall']))
    bank_cell = [Paragraph('<b>Bank details</b><br/>' + '<br/>'.join(bank_lines), styles['ApexBody'])] if bank_lines else ''
    if bank_cell or qr_cell:
        cells = [c for c in (qr_cell, bank_cell) if c] + [signature_cell]
        widths_by_count = {2: [300, 215], 3: [110, 220, 185]}
        payment = Table([cells], colWidths=widths_by_count[len(cells)], hAlign='LEFT')
        payment.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BACKGROUND', (0, 0), (-1, -1), tint), ('TOPPADDING', (0, 0), (-1, -1), padding), ('BOTTOMPADDING', (0, 0), (-1, -1), padding), ('LEFTPADDING', (0, 0), (-1, -1), padding)]))
        elements += [KeepTogether(payment), Spacer(1, 12)]
    for label, key in (('Notes', 'notes'), ('Terms and conditions', 'terms')):
        if brand.get(key): elements += [Paragraph('<b>' + label + '</b>', styles['ApexBody']), Paragraph(safe(brand[key]).replace('\n', '<br/>'), styles['ApexSmall']), Spacer(1, 8)]
    elements.append(Paragraph('Generated from Apex Books. Verify particulars and signature requirements before issue.', styles['ApexSmall']))
    pdf.build(elements)
    return Response(out.getvalue(), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{record.kind}-{record.number or record.id[:8]}.pdf"'})
