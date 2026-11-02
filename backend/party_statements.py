from datetime import date
from decimal import Decimal
from fastapi import Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
def party_balances(m,company_id,party,from_date,to_date,user,session,*,rows=None,posted=None):
    """Canonical statement balances, also used for non-posting credit warnings."""
    account=m.party_report(company_id,from_date,to_date,party.name,user,session)
    if rows is None:
        rows=list(session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.date<=to_date,m.Record.kind.in_(['credit_note','debit_note']))))
        rows=[r for r in rows if r.name.strip().casefold()==party.name.strip().casefold()]
    if posted is None:posted=set(session.scalars(select(m.RecordPosting.record_id).where(m.RecordPosting.company_id==company_id)))
    advances=m.advances_report(company_id,to_date,user,session)
    balances={'receivable':account['closing_receivable'],'payable':account['closing_payable'],'customer_credit':'0','supplier_credit':'0','customer_advance':'0','supplier_advance':'0'}
    for side,note_kind in [('customer','credit_note'),('supplier','debit_note')]:balances[side+'_credit']=str(sum((m.available_credit(m,company_id,r,session,to_date) for r in rows if r.kind==note_kind and r.id in posted),Decimal('0')))
    for side in ('customer','supplier'):balances[side+'_advance']=str(sum((Decimal(r['available']) for r in advances['rows'] if r['side']==side and r['party'].strip().casefold()==party.name.strip().casefold()),Decimal('0')))
    return account,balances

def install(app,m):
    @app.get('/api/companies/{company_id}/parties/{party_id}/statement')
    def statement(company_id:str,party_id:str,from_date:date,to_date:date,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        m.company_for(company_id,user,session)
        party=session.scalar(select(m.Record).where(m.Record.company_id==company_id,m.Record.id==party_id,m.Record.kind=='party'))
        if not party:raise HTTPException(404,'Party not found')
        if from_date>to_date:raise HTTPException(422,'Start date must precede end date')
        rows=list(session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.date<=to_date,m.Record.kind.not_in(['party','item','document_branding','restore_marker','vyapar_backup_archive','recurring_template']))))
        rows=[r for r in rows if r.name.strip().casefold()==party.name.strip().casefold()]
        posted=set(session.scalars(select(m.RecordPosting.record_id).where(m.RecordPosting.company_id==company_id)))
        conversions={r.source_record_id:r.target_record_id for r in session.scalars(select(m.DocumentConversion).where(m.DocumentConversion.company_id==company_id))}
        account,balances=party_balances(m,company_id,party,from_date,to_date,user,session,rows=rows,posted=posted)
        return {'party':m.obj(party),'from_date':str(from_date),'to_date':str(to_date),'balances':balances,'opening_receivable':account['opening_receivable'],'opening_payable':account['opening_payable'],'transactions':[{'id':r.id,'kind':r.kind,'name':r.name,'number':r.number,'date':str(r.date),'amount':str(r.amount),'posted':r.id in posted,'editable':(r.kind in m.DOCUMENTS-m.POSTED_KINDS or r.kind in m.POSTED_KINDS and r.id in posted) and r.id not in conversions and not r.data.get('vyapar_converted'),'converted_to':conversions.get(r.id) or ('source-converted' if r.data.get('vyapar_converted') else None),'outstanding':str(r.amount-m.applied_total(company_id,r.id,session,to_date)) if r.kind in {'sales_invoice','purchase_bill','opening_receivable','opening_payable'} and r.id in posted else None} for r in sorted(rows,key=lambda r:(r.date,r.number,r.id),reverse=True) if r.date>=from_date]}
