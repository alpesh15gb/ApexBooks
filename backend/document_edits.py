"""Versioned document amendments with immutable journal reversal history."""
from datetime import datetime,timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from fastapi import Depends,HTTPException,Request
from sqlalchemy import select,delete,func
from sqlalchemy.orm import Session
from workflow_extensions import retry
import re
from document_inputs import financial_signature,metadata_fields,editable_inputs,merge_display_lines,normalize_input as normalize

def install(app,m):
    @app.put('/api/companies/{company_id}/documents/{record_id}')
    def amend(company_id:str,record_id:str,body:m.RecordInput,request:Request,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        company=m.lock_company(company_id,user,session)
        # Presence matters for expenses: omitted amount preserves the saved value,
        # whereas explicit zero is invalid. Do not alias their retry identities.
        hash_body=body.model_dump(mode='json') if body.kind=='expense' and 'amount' not in body.model_fields_set else None
        if hash_body is not None:hash_body.pop('amount')
        key,digest,old=retry(m,company_id,body,request,session,'amend:'+record_id,hash_body=hash_body)
        if old:return old
        record=session.scalar(select(m.Record).where(m.Record.company_id==company_id,m.Record.id==record_id))
        allowed=m.POSTED_KINDS
        if not record or record.kind not in allowed:raise HTTPException(404,'Editable posted document not found')
        if body.kind!=record.kind:raise HTTPException(422,'Document type cannot change')
        # Older header editors omit amount. Preserve it only when absent; an
        # explicit zero remains a real financial input and fails posting rules.
        if record.kind == 'expense' and 'amount' not in body.model_fields_set:
            body=body.model_copy(update={'amount':record.amount})
        posting=session.scalar(select(m.RecordPosting).where(m.RecordPosting.company_id==company_id,m.RecordPosting.record_id==record.id))
        if not posting:raise HTTPException(409,'This legacy entry needs posting before financial amendment')
        if body.data.get('version',0)!=record.data.get('version',0):raise HTTPException(409,'Document changed; reload before editing')
        m.require_open_period(company_id,record.date,session);m.require_open_period(company_id,body.date,session)
        if not body.name.strip() or len(body.name)>120:raise HTTPException(422,'Enter a party or description up to 120 characters')
        if not body.number.strip() or len(body.number)>16:raise HTTPException(422,'Reference must contain 1–16 characters')
        if session.scalar(select(m.Record.id).where(m.Record.company_id==company_id,m.Record.kind==record.kind,m.Record.number==body.number.strip(),m.Record.id!=record.id)):raise HTTPException(409,'Reference already exists')
        # Clients submit editable inputs, never replacement posting/snapshot fields.
        metadata=metadata_fields(record.kind)
        inputs=editable_inputs(record.kind)
        submitted={k:v for k,v in body.data.items() if k in inputs}
        data={**record.data,**submitted}
        m.validate_active_references(company_id,record.kind,body.name,data,session,record)
        profile=session.get(m.CompanyTaxProfile,company_id)
        def signature(data,amount,party,day):
            return financial_signature(record.kind,company.state_code,profile.mode if profile else 'regular',m.DOCUMENTS,data,amount,party,day)
        intent=signature(data,record.amount,body.name,body.date)!=signature(record.data,record.amount,record.name,record.date)
        if record.kind in {'payment_in','payment_out'} and 'allocations' in body.data:
            existing=[]
            for model in (m.PaymentAllocation,m.PaymentSplitAllocation):existing += [(r.document_id,r.amount) for r in session.scalars(select(model).where(model.company_id==company_id,model.payment_id==record.id))]
            requested = body.data['allocations']
            if not isinstance(requested, list) or len(requested) > 100 or (not requested and not data.get('is_advance')):
                raise HTTPException(422, 'Choose one or more invoices or bills')
            proposed = []
            seen = set()
            for allocation in requested:
                if not isinstance(allocation, dict):raise HTTPException(422, 'Invalid payment allocation')
                target_id = allocation.get('document_id')
                if not isinstance(target_id, str) or not target_id or target_id in seen:
                    raise HTTPException(422, 'Each document must be selected once')
                seen.add(target_id)
                try:
                    value = Decimal(str(allocation.get('amount')))
                    if not value.is_finite() or value <= 0 or value > Decimal('9999999999999.99') or value.as_tuple().exponent < -2:
                        raise ValueError()
                except (ValueError, ArithmeticError):
                    raise HTTPException(422, 'Enter a positive allocation with at most two decimal places')
                proposed.append((target_id, value))
            intent=intent or sorted(existing)!=sorted(proposed)
        # Amount-only expenses use the entered amount just like payments; line-based
        # expenses remain calculated documents and ignore a client's total.
        entered_amount = record.kind not in m.DOCUMENTS or (record.kind == 'expense' and not data.get('lines'))
        intent=intent or (entered_amount and m.money(body.amount)!=record.amount)
        if record.data.get('commerce_connection_id') and (intent or any(data.get(k) != record.data.get(k) for k in metadata-{'notes','terms','due_date'})):
            raise HTTPException(409,'This document is linked to an ecommerce source. Use its source correction / credit workflow to keep both systems reconciled.')
        if intent and record.kind in m.DOCUMENTS and (record.kind!='expense' or data.get('lines')):data,amount=m.calculate(data,company,profile.mode if profile else 'regular',record.kind,session)
        else:amount=m.money(body.amount) if intent else record.amount
        financial=intent
        previous={'name':record.name,'number':record.number,'date':record.date.isoformat(),'amount':str(record.amount),'data':record.data,'journal_id':posting.journal_id}
        version=record.data.get('version',0)+1
        if not financial:
            # A note/header amendment must retain the exact saved tax, valuation,
            # allocations and legal snapshot, including imported rounding values.
            data={**record.data,**{k:v for k,v in submitted.items() if k in metadata}}
            for field,limit in {'party_gstin':15,'party_address':1000,'party_phone':32,'shipping_address':1000,'notes':4000,'terms':8000,'category':100}.items():
                if len(str(data.get(field) or ''))>limit:raise HTTPException(422,'Document '+field.replace('_',' ')+' is too long')
            gstin=str(data.get('party_gstin') or '').strip().upper()
            if gstin and not re.fullmatch(r'\d{2}[A-Z0-9]{13}',gstin):raise HTTPException(422,'Enter a valid 15-character party GSTIN')
            data['party_gstin']=gstin
            if (gstin and gstin!=str(record.data.get('party_gstin') or '').strip().upper()
                    and (profile.mode if profile else 'regular')=='regular'
                    and record.kind in {'sales_invoice','pos','credit_note'}
                    and Decimal(str(data.get('taxable_supply_value',0)))>0
                    and sum((Decimal(str(data.get(field,0))) for field in ('nil_rated_value','exempt_value','non_gst_value')),Decimal('0'))>0):
                raise HTTPException(422,'Issue separate taxable and non-taxable outward documents in this workflow')
            if record.kind=='pos' and data.get('payment_account','cash')=='cash' and 'tender_amount' in submitted:
                tender=normalize('rate',submitted['tender_amount'])
                if tender<record.amount or tender>Decimal('9999999999999.99') or tender.as_tuple().exponent < -2:
                    raise HTTPException(422,'Cash tendered must cover the total and use at most two decimal places')
                data['tender_amount']=str(m.money(tender));data['change_amount']=str(m.money(tender-record.amount))
            if data.get('party_id'):
                party=session.scalar(select(m.Record).where(m.Record.company_id==company_id,m.Record.id==data['party_id'],m.Record.kind=='party'))
                if not party or party.name.strip().casefold()!=body.name.strip().casefold():raise HTTPException(422,'Choose the matching party from this company')
            if data.get('due_date'):
                from datetime import date
                try:due=date.fromisoformat(data['due_date'])
                except (ValueError,TypeError):raise HTTPException(422,'Enter a valid due date')
                if due<body.date:raise HTTPException(422,'Due date cannot precede the document date')
            if 'lines' in submitted:
                data['lines']=merge_display_lines(record.data.get('lines',[]),submitted['lines'])
            record.name=body.name.strip();record.number=body.number.strip();record.data={**data,'version':version,'updated_at':datetime.now(timezone.utc).isoformat()}
        else:
            if record.kind in {'credit_note','debit_note'}:
                posted_settlements=select(m.RecordPosting.record_id).where(m.RecordPosting.company_id==company_id)
                first_settlement=session.scalar(select(func.min(m.Record.date)).where(
                    m.Record.company_id==company_id,m.Record.id.in_(posted_settlements),
                    m.Record.kind.in_(['credit_application','customer_refund','supplier_refund']),
                    m.Record.data['credit_note_id'].as_string()==record.id))
                if first_settlement and body.date>first_settlement:
                    raise HTTPException(422,f'Revised note date cannot follow an existing credit settlement; choose {first_settlement.isoformat()} or earlier')
            if record.data.get('is_advance') and any(row.data.get('advance_id')==record.id for row in session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.kind.in_(['advance_application','advance_refund'])))):raise HTTPException(409,'This advance has settlements. Its description and notes can still be edited.')
            if session.scalar(select(m.BankStatementLine.id).where(m.BankStatementLine.company_id==company_id,m.BankStatementLine.matched_record_id==record.id)) or session.scalar(select(m.BankMatchAllocation.id).where(m.BankMatchAllocation.company_id==company_id,m.BankMatchAllocation.record_id==record.id)):raise HTTPException(409,'Unmatch this bank transaction before changing its financial details')
            allocations=[]
            for model in (m.PaymentAllocation,m.PaymentSplitAllocation):
                allocations+=list(session.scalars(select(model).where(model.company_id==company_id,model.document_id==record.id)))
            if amount<sum((r.amount for r in allocations),Decimal('0')):raise HTTPException(409,'Revised amount cannot be lower than payments and credits already applied')
            for allocation in allocations:
                payment=session.get(m.Record,allocation.payment_id)
                if body.name.strip().casefold()!=record.name.strip().casefold() or body.date>payment.date:raise HTTPException(409,'An allocated document must retain its party and precede its settlements')
            if record.kind in {'sales_invoice','purchase_bill','pos'} and any(r.data.get('applied_to')==record.id for r in session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.kind.in_(['credit_note','debit_note'])))):raise HTTPException(409,'This document has return notes. Its nonfinancial details can still be edited; correct values through the linked notes.')
            movements=list(session.scalars(select(m.StockMovement).where(m.StockMovement.company_id==company_id,m.StockMovement.source_record_id==record.id)))
            item_ids={row.item_id for row in movements}
            if item_ids:
                others=list(session.scalars(select(m.StockMovement).where(m.StockMovement.company_id==company_id,m.StockMovement.item_id.in_(item_ids),m.StockMovement.source_record_id!=record.id,m.StockMovement.date>=record.date)))
                created=record.data.get('created_at')
                def depends(row):
                    source=session.get(m.Record,row.source_record_id)
                    if row.date>record.date:return True
                    # An opening on the same day necessarily preceded the first sale.
                    if source.kind=='stock_opening':return False
                    return not created or not source.data.get('created_at') or source.data['created_at']>created
                if any(depends(row) for row in others):raise HTTPException(409,'Later stock movements depend on this valuation. Header details remain editable; use a return or stock adjustment for quantity/value corrections.')
            old_journal=session.get(m.Journal,posting.journal_id)
            old_lines=list(session.scalars(select(m.JournalLine).where(m.JournalLine.company_id==company_id,m.JournalLine.journal_id==old_journal.id)))
            for row in movements:session.delete(row)
            for model in (m.PaymentAllocation,m.PaymentSplitAllocation):session.execute(delete(model).where(model.company_id==company_id,model.payment_id==record.id))
            session.delete(posting);kind=record.kind;record.kind='_revision_old';session.flush()
            payload={**record.data,**submitted};payload.pop('source_document_id',None);payload.pop('version',None)
            # create_record performs the same validation and posting used by new forms.
            # Its commit is held until the entire revision and audit are ready.
            original_commit=session.commit
            session.commit=session.flush
            try:new=m.save_record(company_id,m.RecordInput(kind=kind,name=body.name,number=body.number,date=body.date,amount=body.amount,data=payload),SimpleNamespace(headers={}),user,session,historical_record=record)
            finally:session.commit=original_commit
            replacement=session.get(m.Record,new['id']);new_data=dict(replacement.data)
            if kind in {'credit_note','debit_note'}:
                used=Decimal(str(previous['data'].get('unallocated_credit',0)))-m.available_credit(m,company_id,record,session)
                if Decimal(str(new_data.get('unallocated_credit',0)))<used:raise HTTPException(409,'Revised note cannot consume credit already applied or refunded')
            new_posting=session.scalar(select(m.RecordPosting).where(m.RecordPosting.record_id==replacement.id));new_posting.record_id=record.id
            session.flush()
            for model,column in ((m.StockMovement,'source_record_id'),(m.PaymentAllocation,'payment_id'),(m.PaymentSplitAllocation,'payment_id')):
                for row in session.scalars(select(model).where(getattr(model,column)==replacement.id)):setattr(row,column,record.id)
            new_journal=session.get(m.Journal,new_posting.journal_id);new_journal.reference='EDIT:'+record.id+':'+str(version)
            reversal=m.Journal(company_id=company_id,date=previous['date'],reference='REV:'+old_journal.id,memo='Document revision '+previous['number'],created_by=user.id)
            from datetime import date
            reversal.date=date.fromisoformat(previous['date']);session.add(reversal);session.flush()
            for line in old_lines:session.add(m.JournalLine(company_id=company_id,journal_id=reversal.id,account_id=line.account_id,debit=line.credit,credit=line.debit))
            session.add(m.JournalReversal(company_id=company_id,original_id=old_journal.id,reversal_id=reversal.id))
            for event in session.scalars(select(m.AuditEvent).where(m.AuditEvent.company_id==company_id,m.AuditEvent.entity_id==replacement.id)):event.entity_id=record.id;event.action='document.revision_posted'
            session.flush();session.delete(replacement);session.flush()
            record.kind=kind;record.name=body.name.strip();record.number=body.number.strip();record.date=body.date;record.amount=amount
            record.data={**new_data,**{k:v for k,v in previous['data'].items() if k.startswith('vyapar_') or k=='source_document_id'},'version':version,'created_at':previous['data'].get('created_at',new_data.get('created_at')),'updated_at':datetime.now(timezone.utc).isoformat()}
        session.add(m.IdempotencyKey(company_id=company_id,key=key,request_hash=digest,record_id=record.id))
        m.audit(session,company_id,user,'document.amended',record.kind,record.id,{'version':version,'financial':financial,'previous':previous})
        session.commit();return {**m.obj(record),'posted':True}
