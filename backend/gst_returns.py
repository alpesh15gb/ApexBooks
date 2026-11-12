"""Book-derived GST preparation reports; no portal data or filing claims."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from fastapi import Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
KEYS=('cgst','sgst','igst')
ZERO=Decimal('0')
def amount(data,key):return Decimal(str(data.get(key,0)))
def utilization(output,credit):
    liability={k:max(ZERO,output[k]) for k in KEYS};remaining={k:max(ZERO,credit[k]) for k in KEYS};used={k:ZERO for k in KEYS};matrix=[]
    def use(source,target,cap=None):
        value=min(remaining[source],liability[target],cap if cap is not None else liability[target])
        if value:remaining[source]-=value;liability[target]-=value;used[target]+=value;matrix.append({'credit':source,'liability':target,'amount':str(value)})
    use('igst','igst')
    for head in ('cgst','sgst'):use('igst',head,max(ZERO,liability[head]-remaining[head]))
    for head in ('cgst','sgst'):use('igst',head)
    for head in ('cgst','sgst'):use(head,head);use(head,'igst')
    return {'cash':{k:str(v) for k,v in liability.items()},'cash_total':str(sum(liability.values())),'credit_carried':{k:str(v) for k,v in remaining.items()},'utilization':matrix}

def install(app,m):
    def build(cid,kind,start,end,user,session,include_documents=False):
        company=m.company_for(cid,user,session)
        if start>end:raise HTTPException(422,'Start date must precede end date')
        profile=session.get(m.CompanyTaxProfile,cid)
        posted=select(m.RecordPosting.record_id).where(m.RecordPosting.company_id==cid)
        records=list(session.scalars(select(m.Record).where(m.Record.company_id==cid,m.Record.id.in_(posted),m.Record.date>=start,m.Record.date<=end).order_by(m.Record.date,m.Record.number)))
        output={k:ZERO for k in KEYS};credit={k:ZERO for k in KEYS};ineligible=ZERO;rows=[];hsn=defaultdict(lambda:{'taxable':ZERO,'tax':ZERO,'quantity':ZERO});outward=[];inward=[];outbase={"taxable":ZERO,"nil":ZERO,"non_gst":ZERO}
        for r in records:
            data=r.data
            if data.get('tax_mode')!='regular':continue
            out=r.kind in {'sales_invoice','pos','credit_note'} or bool(data.get('advance_tax_event'))
            inc=r.kind in {'purchase_bill','expense','debit_note'}
            if not out and not inc:continue
            sign=Decimal('-1') if r.kind in {'credit_note','debit_note'} else Decimal('1')
            taxes={k:sign*amount(data,k) for k in KEYS}
            base=sign*amount(data,'taxable');total=sign*r.amount
            if out:
                for k in KEYS:output[k]+=taxes[k]
                nil=sign*(amount(data,"nil_rated_value")+amount(data,"exempt_value"));non=sign*amount(data,"non_gst_value")
                outbase["nil"]+=nil;outbase["non_gst"]+=non;outbase["taxable"]+=base-nil-non
                gstin=str(data.get('party_gstin',''));threshold=Decimal('100000') if r.date>=date(2024,8,1) else Decimal('250000')
                section='CDNR' if r.kind=='credit_note' and gstin else 'CDNUR' if r.kind=='credit_note' else 'AT / advance adjustment' if data.get('advance_tax_event') else 'B2B' if gstin else 'B2CL' if amount(data,'igst')>0 and r.amount>threshold else 'B2CS'
                if r.kind=='credit_note' and not gstin:
                    original=session.get(m.Record,data.get('applied_to')) if data.get('applied_to') else None
                    if original and original.company_id==cid:
                        original_threshold=Decimal('100000') if original.date>=date(2024,8,1) else Decimal('250000')
                        if not original.data.get('party_gstin') and not (amount(original.data,'igst')>0 and original.amount>original_threshold):
                            section='B2CS · credit adjustment'
                if not any(taxes.values()) and any(amount(data,k) for k in ('nil_rated_value','exempt_value','non_gst_value')):section='8 · Nil / exempt / non-GST'
                outward.append({'date':r.date.isoformat(),'number':r.number,'party':r.name,'gstin':gstin,'place':data.get('place_of_supply',''),'section':section,'taxable':str(base),**{k:str(v) for k,v in taxes.items()},'total':str(total)})
                for line in data.get('lines',[]) if kind != 'gstr2a' else []:
                    if data.get('advance_tax_event'):continue
                    value=hsn[(str(line.get('hsn','')),str(line.get('gst_rate',0)))];value['taxable']+=sign*amount(line,'taxable');value['tax']+=sign*amount(line,'tax');value['quantity']+=sign*Decimal(str(line.get('quantity',0)))
            if inc:
                pending={k:sign*Decimal(str(data.get('pending_input_'+k,data.get(k,0)))) for k in KEYS}
                blocked=sign*amount(data,'input_tax_ineligible');ineligible+=blocked
                for k in KEYS:credit[k]+=pending[k]
                inward.append({'date':r.date.isoformat(),'number':r.number,'party':r.name,'gstin':data.get('party_gstin',''),'place':data.get('place_of_supply',''),'section':'Purchase return' if r.kind=='debit_note' else 'Expense bill' if r.kind=='expense' else 'Purchase bill','taxable':str(base),**{k:str(v) for k,v in taxes.items()},'total':str(total),'proposed_itc':str(sum(pending.values())),'ineligible':str(blocked)})
                if kind == 'gstr2a':
                    for line in data.get('lines', []):
                        value = hsn[(str(line.get('hsn', '')), str(line.get('gst_rate', 0)))]
                        value['taxable'] += sign * amount(line, 'taxable')
                        value['tax'] += sign * amount(line, 'tax')
                        value['quantity'] += sign * Decimal(str(line.get('quantity', 0)))
        estimate=utilization(output,credit)
        standard=kind.upper().replace('GSTR','GSTR-')
        if kind=='gstr1':
            rows=outward;title='GSTR-1 · outward supplies working paper';columns=[('date','Date'),('number','Document'),('party','Party'),('gstin','GSTIN'),('place','POS'),('section','Section'),('taxable','Base value'),('cgst','CGST'),('sgst','SGST/UTGST'),('igst','IGST'),('total','Total')]
        elif kind=='gstr2a':
            rows=inward;title='GSTR-2A-style purchase register · from entered bills';columns=[('date','Date'),('number','Bill / note'),('party','Supplier'),('gstin','GSTIN'),('section','Type'),('taxable','Base value'),('cgst','CGST'),('sgst','SGST/UTGST'),('igst','IGST'),('proposed_itc','Book ITC'),('ineligible','Ineligible')]
        else:
            title='GSTR-3B · book-derived working paper';columns=[('section','Table / working'),('taxable','Base value'),('cgst','CGST'),('sgst','SGST/UTGST'),('igst','IGST')]
            taxable=sum((Decimal(r['taxable']) for r in outward),ZERO)
            rows=[{'section':'3.1(a) · Taxable outward supplies and advance adjustments','taxable':str(outbase['taxable']),**{k:str(v) for k,v in output.items()}},{'section':'3.1(c) · Nil-rated and exempt outward supplies','taxable':str(outbase['nil']),**{k:'0' for k in KEYS}},{'section':'3.1(e) · Non-GST outward supplies','taxable':str(outbase['non_gst']),**{k:'0' for k in KEYS}},{'section':'4(A)(5) · Proposed book ITC, net of purchase returns','taxable':'0',**{k:str(v) for k,v in credit.items()}},{'section':'Estimated ITC utilization','taxable':'0',**{k:str(max(ZERO,output[k])-Decimal(estimate['cash'][k])) for k in KEYS}},{'section':'Estimated cash payable','taxable':'0',**estimate['cash']},{'section':'Input credit carried forward','taxable':'0',**estimate['credit_carried']}]
        sections=defaultdict(lambda:{'documents':0,'taxable':ZERO,'tax':ZERO})
        for row in inward if kind == 'gstr2a' else outward:
            v=sections[row['section']];v['documents']+=1;v['taxable']+=Decimal(row['taxable']);v['tax']+=sum((Decimal(row[k]) for k in KEYS),ZERO)
        result={'title':title,'standard':standard,'from_date':start.isoformat(),'to_date':end.isoformat(),'applicable':bool(profile and profile.mode=='regular'),'columns':[{'key':k,'label':v} for k,v in columns],'rows':rows,'output':{k:str(v) for k,v in output.items()},'book_itc':{k:str(v) for k,v in credit.items()},'ineligible':str(ineligible),**estimate,'sections':{k:{f:str(v) if isinstance(v,Decimal) else v for f,v in value.items()} for k,value in sections.items()},'hsn':[{'hsn':key[0],'rate':key[1],**{k:str(v) for k,v in value.items()}} for key,value in hsn.items()],'note':'Prepared from app entries. Purchase-derived 2A is not the portal GSTR-2A. Book ITC is provisional until eligibility and GSTR-2B verification; these reports do not file returns.'}
        missing_gstin = [row for row in inward if not str(row['gstin'] or '').strip() and Decimal(row['proposed_itc']) != ZERO]
        result['itc_review_warnings'] = [{'code':'missing_supplier_gstin', 'number':row['number'], 'date':row['date'], 'party':row['party'], 'book_itc':row['proposed_itc']} for row in missing_gstin]
        if missing_gstin:
            result['itc_review_note'] = f"{len(missing_gstin)} purchase/expense/return document(s) contributing to provisional book ITC have no supplier GSTIN. Review the source invoices, supplier registration and applicable eligibility rules, and verify GSTR-2B where applicable before relying on this credit or estimated cash offset. No eligibility decision or amount adjustment has been made."
            result['note'] += ' ' + result['itc_review_note']
        from gst_exports import prepare
        documents=[]
        for record in records:
            if record.data.get('tax_mode')!='regular':continue
            if record.kind not in {'sales_invoice','pos','credit_note','purchase_bill','expense','debit_note'} and not record.data.get('advance_tax_event'):continue
            source=session.get(m.Record,record.data.get('applied_to') or record.data.get('advance_id')) if record.data.get('applied_to') or record.data.get('advance_id') else None
            parent={'date':source.date.isoformat(),'amount':str(source.amount),'number':source.number,'data':source.data} if source and source.company_id==cid else None
            documents.append({'id':record.id,'kind':record.kind,'date':record.date.isoformat(),'number':record.number or '', 'party':record.name,'amount':str(record.amount),'data':record.data,'parent':parent})
        prepared=prepare(kind,result,company,documents)
        result['export_info']=prepared['info']
        if kind=='gstr3b':result['return_tables']=prepared['sheets']
        if include_documents:result['_export']=prepared
        return result

    @app.get('/api/companies/{company_id}/reports/gst-payable')
    def payable(company_id:str,from_date:m.DateType,to_date:m.DateType,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        return build(company_id,'gstr3b',from_date,to_date,user,session)

    # Register explicit paths, so generic report/export handlers cannot shadow them.
    def report(company_id:str,report_name:str,from_date:m.DateType,to_date:m.DateType,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        if report_name not in {'gstr1','gstr2a','gstr3b'}:raise HTTPException(404,'Unknown GST report')
        return build(company_id,report_name,from_date,to_date,user,session)
    def export(company_id:str,report_name:str,fmt:str,from_date:m.DateType,to_date:m.DateType,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        if report_name not in {'gstr1','gstr2a','gstr3b'}:raise HTTPException(404,'Unknown GST report')
        if fmt not in {'xlsx','pdf','json'}:raise HTTPException(404,'Unsupported GST export format')
        data=build(company_id,report_name,from_date,to_date,user,session,True)
        from gst_exports import export_response
        return export_response(report_name,data,fmt)
    # These paths have a dedicated namespace to avoid intercepting other reports.
    app.add_api_route('/api/companies/{company_id}/gst-returns/{report_name}.{fmt}',export,methods=['GET'])
    app.add_api_route('/api/companies/{company_id}/gst-returns/{report_name}',report,methods=['GET'])
