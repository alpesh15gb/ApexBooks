"""Read-only replenishment and explicit pricing/due-date suggestions.

Metadata edits never post journals; suggestions never silently change documents.
"""
from datetime import date,timedelta
from decimal import Decimal
from fastapi import Depends,HTTPException,Query
from sqlalchemy import select,func,case,cast,exists
from sqlalchemy.orm import Session


def install(app,m):
    def master(cid,rid,kind,session):
        row=session.scalar(select(m.Record).where(m.Record.company_id==cid,m.Record.id==rid,m.Record.kind==kind))
        if not row:raise HTTPException(404,kind.title()+' not found in this company')
        return row

    @app.get('/api/companies/{company_id}/reports/reorder')
    def reorder(company_id:str,as_of:date|None=None,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        m.company_for(company_id,user,session);day=as_of or date.today()
        items=list(session.scalars(select(m.Record).where(m.Record.company_id==company_id,m.Record.kind=='item')))
        items=[r for r in items if r.data.get('track_stock') and r.data.get('item_type','goods')=='goods' and r.data.get('low_stock_threshold') is not None]
        totals={}
        if items:
            totals={iid:(quantity,unvalued) for iid,quantity,unvalued in session.execute(select(m.StockMovement.item_id,func.sum(m.StockMovement.quantity),func.sum(case((m.StockMovement.cost_value.is_(None),1),else_=0))).where(m.StockMovement.company_id==company_id,m.StockMovement.item_id.in_([r.id for r in items]),m.StockMovement.date<=day).group_by(m.StockMovement.item_id))}
        rows=[]
        for item in items:
            try:
                threshold=Decimal(str(item.data['low_stock_threshold']))
                if not threshold.is_finite() or threshold<0 or threshold>Decimal('999999999999.999') or threshold.normalize().as_tuple().exponent < -3:raise ValueError()
            except (ValueError,ArithmeticError):raise HTTPException(409,'Review invalid legacy low-stock threshold for '+item.name)
            quantity,unvalued=totals.get(item.id,(Decimal('0'),0))
            if quantity>threshold:continue
            rows.append({'item_id':item.id,'name':item.name,'unit':item.data.get('unit',''),'on_hand':str(quantity),'low_stock_threshold':str(threshold),'suggested_quantity':str(max(threshold-quantity,Decimal('0'))),'purchase_rate':str(item.data.get('purchase_rate','0')),'valuation_status':'unvalued' if unvalued else 'negative' if quantity<0 else 'valued'})
        return {'as_of':day.isoformat(),'rows':sorted(rows,key=lambda r:r['name'].casefold()),'total_low_stock':len(rows)}

    @app.get('/api/companies/{company_id}/parties/{party_id}/due-date')
    def due_date(company_id:str,party_id:str,document_date:date,user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        m.company_for(company_id,user,session);party=master(company_id,party_id,'party',session)
        days=party.data.get('payment_terms_days');suggested=None
        if days is not None:
            if isinstance(days,bool) or not isinstance(days,int) or not 0<=days<=3650:raise HTTPException(409,'Review invalid legacy payment terms before using a default')
            try:suggested=(document_date+timedelta(days=days)).isoformat()
            except OverflowError:raise HTTPException(422,'Suggested due date exceeds the supported calendar')
        return {'party_id':party_id,'payment_terms_days':days,'document_date':document_date.isoformat(),'suggested_due_date':suggested}

    @app.get('/api/companies/{company_id}/parties/{party_id}/item-prices')
    def item_prices(company_id:str,party_id:str,item_id:str,side:str=Query(pattern='^(sales|purchase)$'),user:m.User=Depends(m.current_user),session:Session=Depends(m.db)):
        m.company_for(company_id,user,session);master(company_id,party_id,'party',session);item=master(company_id,item_id,'item',session)
        kinds=['sales_invoice','pos'] if side=='sales' else ['purchase_bill']
        reversed_journals=select(m.JournalReversal.original_id).where(m.JournalReversal.company_id==company_id)
        posted=select(m.RecordPosting.record_id).where(m.RecordPosting.company_id==company_id,m.RecordPosting.journal_id.not_in(reversed_journals))
        query=select(m.Record).where(m.Record.company_id==company_id,m.Record.kind.in_(kinds),m.Record.id.in_(posted),m.Record.data['party_id'].as_string()==party_id)
        if session.bind.dialect.name=='postgresql':
            from sqlalchemy.dialects.postgresql import JSONB
            query=query.where(cast(m.Record.data['lines'],JSONB).contains([{'item_id':item_id}]))
        else:
            line=func.json_each(m.Record.data,'$.lines').table_valued('value').alias('price_line')
            query=query.where(exists(select(1).select_from(line).where(func.json_extract(line.c.value,'$.item_id')==item_id)))
        records=session.scalars(query.order_by(m.Record.date.desc(),func.coalesce(m.Record.data['created_at'].as_string(), '').desc(),m.Record.id.desc()).limit(5))
        history=[]
        for record in records:
            for index,line in reversed(list(enumerate(record.data.get('lines',[])))):
                if line.get('item_id')!=item_id:continue
                history.append({'record_id':record.id,'number':record.number,'date':record.date.isoformat(),'line_index':index,'quantity':str(line.get('quantity','0')),'rate':str(line.get('rate','0')),'price_includes_tax':line.get('price_includes_tax') is True,'gst_rate':str(line.get('gst_rate','0')),'discount_percent':str(line.get('discount_percent','0')),'discount_amount':str(line.get('discount_amount','0'))})
                if len(history)==5:break
            if len(history)==5:break
        default=str(item.data.get('sale_rate' if side=='sales' else 'purchase_rate','0'))
        return {'party_id':party_id,'item_id':item_id,'side':side,'default_rate':default,'history':history,'suggested_rate':history[0]['rate'] if history else default,'suggested_price_includes_tax':history[0]['price_includes_tax'] if history else False,'source':'last_posted' if history else 'item_default','requires_confirmation':True}
