from statement_order import record_key, posting_timestamp, ORDERING_NOTE
from datetime import date
from decimal import Decimal
from fastapi import Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

def unallocated_receipt(record):
    return record.kind == 'payment_in' and record.data.get('receipt_purpose') == 'unallocated'


def party_balances(m,company_id,party,from_date,to_date,user,session,*,rows=None,posted=None):
    """Canonical statement balances, also used for non-posting credit warnings."""
    account=m.party_report(company_id,from_date,to_date,party.name,user,session)
    if rows is None:
        rows=list(session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.date<=to_date,m.Record.kind.in_(['credit_note','debit_note']))))
        rows=[r for r in rows if r.name.strip().casefold()==party.name.strip().casefold()]
    if posted is None:posted=set(session.scalars(select(m.RecordPosting.record_id).where(m.RecordPosting.company_id==company_id)))
    advances=m.advances_report(company_id,to_date,user,session)
    balances={'receivable':account['closing_receivable'],'payable':account['closing_payable'],'customer_credit':'0','supplier_credit':'0','customer_advance':'0','supplier_advance':'0'}
    receipts=session.execute(select(m.Record.name,m.Record.amount).where(
        m.Record.company_id==company_id, m.Record.kind=='payment_in', m.Record.id.in_(posted),
        m.Record.date<=to_date, m.Record.data['receipt_purpose'].as_string()=='unallocated'))
    unallocated = sum((value for name,value in receipts if name.strip().casefold()==party.name.strip().casefold()), Decimal('0'))
    if unallocated:
        balances['unallocated_receipts'] = str(unallocated)
    for side,note_kind in [('customer','credit_note'),('supplier','debit_note')]:balances[side+'_credit']=str(sum((m.available_credit(m,company_id,r,session,to_date) for r in rows if r.kind==note_kind and r.id in posted),Decimal('0')))
    for side in ('customer','supplier'):balances[side+'_advance']=str(sum((Decimal(r['available']) for r in advances['rows'] if r['side']==side and r['party'].strip().casefold()==party.name.strip().casefold()),Decimal('0')))
    return account,balances

LEDGER_KINDS={'sales_invoice','credit_note','payment_in','purchase_bill','debit_note','payment_out','advance_application','opening_receivable','opening_payable','credit_application'}
VOUCHER_TYPES={'sales_invoice':'Sales','credit_note':'Credit Note','payment_in':'Receipt','purchase_bill':'Purchase','debit_note':'Debit Note','payment_out':'Payment','advance_application':'Journal','credit_application':'Journal','opening_receivable':'Opening','opening_payable':'Opening'}

def ledger_effect(r):
    """(debit, credit) on the party's ledger, by the same rules as the party report's receivable and payable."""
    unallocated=Decimal(str(r.data.get('unallocated_credit',0))) if r.kind in {'credit_note','debit_note'} else Decimal('0')
    if r.kind in {'sales_invoice','opening_receivable'}:return r.amount,Decimal('0')
    if r.kind in {'purchase_bill','opening_payable'}:return Decimal('0'),r.amount
    if r.kind in {'credit_note','payment_in'}:return Decimal('0'),r.amount-unallocated
    if r.kind in {'debit_note','payment_out'}:return r.amount-unallocated,Decimal('0')
    return (Decimal('0'),r.amount) if r.data.get('payment_kind')=='payment_in' else (r.amount,Decimal('0'))

def correction_history(m, company_id, party_name, from_date, to_date, session):
    records = session.scalars(select(m.Record).where(m.Record.company_id==company_id,
        m.Record.kind.in_(['payment_in','advance_application']),
        m.Record.data['receipt_correction_superseded'].as_string().is_not(None),
        m.Record.date.between(from_date,to_date)).order_by(m.Record.date,m.Record.number,m.Record.id))
    history = []
    for row in records:
        if party_name and row.name.strip().casefold() != party_name.strip().casefold():
            continue
        allocations = ', '.join(f"{a['invoice']} ({lakh_format(a['amount'])})"
                                for a in row.data.get('receipt_correction_allocations', []) if a.get('invoice'))
        document = 'receipt' if row.kind == 'payment_in' else 'advance application'
        particulars = f'Superseded {document} {lakh_format(row.amount)}'
        history.append({'id':row.id,'date':str(row.date),'party':row.name,'number':row.number,
                        'details':f'{particulars} · {allocations}' if allocations else particulars})
    return history


def party_ledger(m,company_id,party,from_date,to_date,session,include_corrections=False):
    """Tally-style ledger for one party: debit means they owe you, credit means you owe them."""
    name=party.name.strip().casefold()
    postings=select(m.RecordPosting.record_id).where(m.RecordPosting.company_id==company_id)
    records=[r for r in session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.id.in_(postings),m.Record.kind.in_(LEDGER_KINDS),m.Record.date<=to_date))
             if r.name.strip().casefold()==name and (not r.data.get('is_advance') or r.kind=='payment_in')]
    by_id={r.id:r for r in records}
    banks={b.id:b.name for b in session.scalars(select(m.BankAccount).where(m.BankAccount.company_id==company_id))}
    def counter(r):
        if r.kind in {'payment_in','payment_out'}:
            if r.data.get('vyapar_settlement_discount'):return 'Discount'
            return banks.get(r.data.get('bank_account_id')) or 'Bank' if r.data.get('payment_account')=='bank' else 'Cash'
        return {'sales_invoice':'Sales','purchase_bill':'Purchase','credit_note':'Sales Return','debit_note':'Purchase Return','opening_receivable':'Opening balance','opening_payable':'Opening balance'}.get(r.kind,'Advance or credit applied')
    def number(r):
        # A payment taken on the invoice itself carries the invoice's number, not an internal import reference.
        source=by_id.get(r.data.get('source_document_id'))
        return source.number if source is not None and str(r.number).startswith('VYP-PAY-') else r.number
    def line(r):
        if r.data.get('is_advance') or unallocated_receipt(r):
            return r,Decimal('0'),Decimal('0')
        debit,credit=ledger_effect(r)
        return r,debit,credit
    detail_ids = {r.id for r in records if r.kind in {'payment_in', 'advance_application'} and r.date >= from_date}
    linked = {}
    for model in (m.PaymentAllocation, m.PaymentSplitAllocation):
        for link in session.scalars(select(model).where(model.company_id==company_id,model.payment_id.in_(detail_ids))):
            target = by_id.get(link.document_id)
            if target:
                linked.setdefault(link.payment_id, []).append((target.number, link.amount))
    receipt_ids = {r.id for r in records if r.kind == 'payment_in' and r.date >= from_date and not r.data.get('utr')}
    references = {}
    for rid, ref in session.execute(select(m.BankStatementLine.matched_record_id, m.BankStatementLine.reference).where(
            m.BankStatementLine.company_id==company_id, m.BankStatementLine.matched_record_id.in_(receipt_ids))):
        if ref:
            references.setdefault(rid, set()).add(ref)
    for rid, ref in session.execute(select(m.BankMatchAllocation.record_id, m.BankStatementLine.reference)
            .join(m.BankStatementLine, m.BankStatementLine.id==m.BankMatchAllocation.statement_line_id)
            .where(m.BankMatchAllocation.company_id==company_id, m.BankStatementLine.company_id==company_id,
                   m.BankMatchAllocation.record_id.in_(receipt_ids))):
        if ref:
            references.setdefault(rid, set()).add(ref)
    lines=[entry for entry in map(line,records) if entry[1] or entry[2] or entry[0].kind=='payment_in']
    lines.sort(key=lambda e:record_key(e[0]))
    opening=sum((d-c for r,d,c in lines if r.date<from_date),Decimal('0'))
    balance=opening;rows=[];total_debit=total_credit=total_receipts=Decimal('0')
    has_held_receipts = False
    for r,debit,credit in lines:
        if r.date<from_date:continue
        balance+=debit-credit;total_debit+=debit;total_credit+=credit
        if r.kind == 'payment_in':
            total_receipts += r.amount
        details = []
        if r.kind == 'payment_in' and (r.data.get('is_advance') or unallocated_receipt(r)):
            has_held_receipts = True
            purpose = 'Unallocated customer receipt' if unallocated_receipt(r) else 'Customer advance'
            details.append(f'{purpose} {lakh_format(r.amount)}')
        if r.kind == 'payment_in':
            refs = [str(r.data['utr'])] if r.data.get('utr') else sorted(references.get(r.id, ()))
            details.extend('UTR ' + ref for ref in refs)
        details.extend(f'{ref} ({lakh_format(value)})' for ref,value in sorted(linked.get(r.id, [])))
        rows.append({'id':r.id,'kind':r.kind,'date':r.date.isoformat(),'posting_timestamp':posting_timestamp(r),'particulars':('To ' if debit else 'By ')+counter(r),'voucher_type':VOUCHER_TYPES[r.kind],'voucher_number':number(r),
            'details': ' · '.join(details),
            'debit':str(debit) if debit else '','credit':str(credit) if credit else '','balance':str(abs(balance)),'balance_side':'Dr' if balance>0 else 'Cr' if balance<0 else ''})
    history = correction_history(m, company_id, name, from_date, to_date, session) if include_corrections else []
    side=lambda v:'Dr' if v>0 else 'Cr' if v<0 else ''
    return {'party':party.name,'from_date':from_date.isoformat(),'to_date':to_date.isoformat(),
        'ordering_note':ORDERING_NOTE,'opening':{'amount':str(abs(opening)),'side':side(opening)},'rows':rows,
        'totals':{'debit':str(total_debit),'credit':str(total_credit),'receipts':str(total_receipts)},
        'has_held_receipts':has_held_receipts,'correction_history':history,
        'closing':{'amount':str(abs(balance)),'side':side(balance)}}

def lakh_format(value):
    """Indian digit grouping: 1234567.5 -> 12,34,567.50"""
    text=f'{Decimal(value):.2f}';whole,paise=text.split('.')
    groups=[whole[-3:]];whole=whole[:-3]
    while whole:groups.insert(0,whole[-2:]);whole=whole[:-2]
    return ','.join(groups)+'.'+paise

def ledger_table(ledger):
    """Export rows, ending with Tally's opening balance, current total and closing balance."""
    pretty=lambda iso:date.fromisoformat(iso).strftime('%d-%b-%Y')
    balance=lambda amount,side:(lakh_format(amount)+' '+side).strip()
    rows=[['','Opening balance','','','','',balance(ledger['opening']['amount'],ledger['opening']['side'])]]
    rows+=[[pretty(r['date']),' · '.join(filter(None,(r['particulars'],r['details']))),r['voucher_type'],r['voucher_number'],r['debit'],r['credit'],balance(r['balance'],r['balance_side'])] for r in ledger['rows']]
    if ledger['has_held_receipts']:
        rows.append(['',f"Customer receipts received {lakh_format(ledger['totals']['receipts'])}",'','','','',''])
    rows.append(['','Current total','','',ledger['totals']['debit'],ledger['totals']['credit'],''])
    rows.append(['','Closing balance','','','','',balance(ledger['closing']['amount'],ledger['closing']['side'])])
    if ledger['correction_history']:
        rows.append(['','Correction history','','','','',''])
        rows.extend([pretty(r['date']),r['details'],'History',r['number'],'','',''] for r in ledger['correction_history'])
    return ['Date','Particulars','Vch Type','Vch No.','Debit','Credit','Balance'],rows

def install(app,m):
    def ledger_party(company_id,party_id,from_date,to_date,session):
        party=session.scalar(select(m.Record).where(m.Record.company_id==company_id,m.Record.id==party_id,m.Record.kind=='party'))
        if not party:raise HTTPException(404,'Party not found')
        m.resolve_party(company_id,party.name,session)
        if from_date>to_date:raise HTTPException(422,'Start date must precede end date')
        return party

    @app.get('/api/companies/{company_id}/parties/{party_id}/ledger')
    def ledger_view(company_id:str,party_id:str,from_date:date,to_date:date,include_corrections:bool=False,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        m.company_for(company_id,user,session)
        return party_ledger(m,company_id,ledger_party(company_id,party_id,from_date,to_date,session),from_date,to_date,session,include_corrections)

    @app.get('/api/companies/{company_id}/parties/{party_id}/statement.{fmt}')
    def ledger_export(company_id:str,party_id:str,fmt:str,from_date:date,to_date:date,include_corrections:bool=False,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        company=m.company_for(company_id,user,session)
        party=ledger_party(company_id,party_id,from_date,to_date,session)
        ledger=party_ledger(m,company_id,party,from_date,to_date,session,include_corrections)
        headers,rows=ledger_table(ledger)
        period=date.fromisoformat(str(from_date)).strftime('%d-%b-%Y')+' to '+date.fromisoformat(str(to_date)).strftime('%d-%b-%Y')
        notes = [ORDERING_NOTE]
        if ledger['has_held_receipts']:
            notes.append('Advance and unallocated receipts appear in particulars. The debit and credit columns track receivables and payables.')
        return m.export_table(company.name,f'Ledger {party.name} {period}',headers,rows,fmt,'party-statement',notes=notes)

    @app.get('/api/companies/{company_id}/parties/balances')
    def balances(company_id:str,as_of:date|None=None,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        """Closing receivable/payable per party for list views; same rules as the party report in one pass."""
        from business_calendar import business_today
        m.company_for(company_id,user,session);day=as_of or business_today()
        postings=select(m.RecordPosting.record_id).where(m.RecordPosting.company_id==company_id)
        kinds={'sales_invoice','credit_note','payment_in','purchase_bill','debit_note','payment_out','advance_application','opening_receivable','opening_payable','credit_application','customer_refund','supplier_refund'}
        totals={}
        for r in session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.id.in_(postings),m.Record.kind.in_(kinds),m.Record.date<=day)):
            if r.data.get('is_advance') or unallocated_receipt(r):continue
            key=r.name.strip().casefold();side=totals.setdefault(key,[Decimal('0'),Decimal('0')])
            unallocated=Decimal(str(r.data.get('unallocated_credit',0))) if r.kind in {'credit_note','debit_note'} else Decimal('0')
            if r.kind in {'sales_invoice','opening_receivable'}:side[0]+=r.amount
            elif r.kind in {'credit_note','payment_in'}:side[0]-=r.amount-unallocated
            elif r.kind in {'purchase_bill','opening_payable'}:side[1]+=r.amount
            elif r.kind in {'advance_application','credit_application'} and r.data.get('payment_kind')=='payment_in':side[0]-=r.amount
            elif r.kind in {'advance_application','credit_application'}:side[1]-=r.amount
            elif r.kind in {'debit_note','payment_out'}:side[1]-=r.amount-unallocated
        rows=[]
        parties=list(session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.kind=='party')))
        names=[party.name.strip().casefold() for party in parties]
        if len(names)!=len(set(names)):raise HTTPException(409,'Ambiguous legacy party names require review before calculating master balances')
        for party in parties:
            receivable,payable=totals.get(party.name.strip().casefold(),[Decimal('0'),Decimal('0')])
            rows.append({'party_id':party.id,'name':party.name,'receivable':str(receivable),'payable':str(payable),'net':str(receivable-payable)})
        return {'as_of':day.isoformat(),'rows':rows,
                'totals':{'to_receive':str(sum((Decimal(r['net']) for r in rows if Decimal(r['net'])>0),Decimal('0'))),
                          'to_pay':str(sum((-Decimal(r['net']) for r in rows if Decimal(r['net'])<0),Decimal('0')))}}

    @app.get('/api/companies/{company_id}/parties/{party_id}/statement')
    def statement(company_id:str,party_id:str,from_date:date,to_date:date,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        m.company_for(company_id,user,session)
        party=session.scalar(select(m.Record).where(m.Record.company_id==company_id,m.Record.id==party_id,m.Record.kind=='party'))
        if not party:raise HTTPException(404,'Party not found')
        m.resolve_party(company_id,party.name,session)
        if from_date>to_date:raise HTTPException(422,'Start date must precede end date')
        rows=list(session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.date<=to_date,m.Record.kind.not_in(['party','item','document_branding','restore_marker','vyapar_backup_archive','recurring_template','inventory_setup']))))
        rows=[r for r in rows if r.name.strip().casefold()==party.name.strip().casefold() and not r.data.get('cancelled')]
        posted=set(session.scalars(select(m.RecordPosting.record_id).where(m.RecordPosting.company_id==company_id)))
        conversions={r.source_record_id:r.target_record_id for r in session.scalars(select(m.DocumentConversion).where(m.DocumentConversion.company_id==company_id))}
        account,balances=party_balances(m,company_id,party,from_date,to_date,user,session,rows=rows,posted=posted)
        return {'party':m.obj(party),'from_date':str(from_date),'to_date':str(to_date),'balances':balances,'opening_receivable':account['opening_receivable'],'opening_payable':account['opening_payable'],'transactions':[{'id':r.id,'kind':r.kind,'name':r.name,'number':r.number,'date':str(r.date),'amount':str(r.amount),'posted':r.id in posted,'editable':(r.kind in m.DOCUMENTS-m.POSTED_KINDS or r.kind in m.POSTED_KINDS and r.id in posted) and r.id not in conversions and not r.data.get('vyapar_converted') and not r.data.get('receipt_correction_id') and not unallocated_receipt(r),'converted_to':conversions.get(r.id) or ('source-converted' if r.data.get('vyapar_converted') else None),'outstanding':str(r.amount-m.applied_total(company_id,r.id,session,to_date)) if r.kind in {'sales_invoice','purchase_bill','opening_receivable','opening_payable'} and r.id in posted else None} for r in sorted(rows,key=lambda r:(r.date,r.number,r.id),reverse=True) if r.date>=from_date]}
