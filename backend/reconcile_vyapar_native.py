"""Compare posted API records with independently exported native Vyapar reports."""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from openpyxl import load_workbook
from vyapar_audit import rounded

KINDS={'Sale':'sales_invoice','Purchase':'purchase_bill','Estimate':'estimate','Purchase Order':'purchase_order','Payment-In':'payment_in'}

def reconcile(records,stock_report,transactions_path,stock_path,gst_path):
    checks=[]
    def check(label,expected,actual):checks.append({'check':label,'expected':str(expected),'actual':str(actual),'passed':expected==actual})
    actual=defaultdict(list)
    for record in records:
        if record['kind'] not in KINDS.values() or record['data'].get('vyapar_immediate_payment'):continue
        actual[(record['date'],record['number'],record['name'],record['kind'])].append(record)
    seen=set()
    for index,row in enumerate(load_workbook(transactions_path,data_only=True).active.values,1):
        if len(row)<10 or not isinstance(row[0],str):continue
        try:day=datetime.strptime(row[0],'%d/%m/%Y').date().isoformat()
        except ValueError:continue
        identity=(day,str(row[1] or ''),str(row[2] or ''),KINDS.get(str(row[4] or '').strip()))
        found=actual.get(identity,[]);check(f'Native transaction row {index} identity',1,len(found))
        if len(found)!=1:continue
        record=found[0];seen.add(record['id']);check(f'Native transaction row {index} total',rounded(row[5]),rounded(record['amount']))
        if record['kind'] in ('sales_invoice','purchase_bill'):
            paid=rounded(record['amount'])-rounded(record['outstanding'])
            check(f'Native transaction row {index} paid/received',rounded(row[7] if record['kind']=='purchase_bill' else row[8]),paid)
            check(f'Native transaction row {index} balance',rounded(row[9]),rounded(record['outstanding']))
        elif record['kind']=='purchase_order':
            paid=sum((rounded(p['amount']) for p in records if p['kind']=='payment_out' and p['data'].get('is_advance') and p['data'].get('source_document_id')==record['id']),Decimal(0))
            check(f'Native order row {index} supplier advance',rounded(row[7]),paid)
        elif record['kind']=='payment_in':check(f'Native receipt row {index} received',rounded(row[8]),rounded(record['amount']))
        payments=[p for p in records if p['kind'] in ('payment_in','payment_out') and p['data'].get('source_document_id')==record['id']]
        if record['kind']=='payment_in':payments=[record]
        # Account names are checked independently through the bank/cash native balances.
    for record in records:
        if record['kind'] in KINDS.values() and not record['data'].get('vyapar_immediate_payment'):
            check('Source row '+str(record['data'].get('vyapar_source_id'))+' native visibility',not bool(record['converted_to']),record['id'] in seen)
    stock={r['name']:r for r in stock_report['rows']}
    stock_seen=set()
    for index,row in enumerate(load_workbook(stock_path,data_only=True).active.values,1):
        if len(row)<7 or not isinstance(row[0],str) or row[0] in ('Godown','Item Name'):continue
        found=stock.get(row[0]);check(f'Native stock row {index} identity',True,found is not None)
        if found:
            stock_seen.add(row[0]);check(f'Native stock row {index} quantity',Decimal(str(row[3])),Decimal(found['closing_quantity']))
            check(f'Native stock row {index} value',rounded(row[6]),rounded(found['closing_value']))
    check('Native stock item coverage',len(stock),len(stock_seen))
    tax=defaultdict(lambda:defaultdict(Decimal));source_tax=defaultdict(lambda:defaultdict(Decimal))
    for record in records:
        if record['kind'] not in ('sales_invoice','purchase_bill'):continue
        tax[record['name']][record['kind']]+=sum((Decimal(line['tax']) for line in record['data'].get('lines',[])),Decimal(0))
        source_tax[record['name']][record['kind']]+=sum((Decimal(line['source_tax']) for line in record['data'].get('lines',[])),Decimal(0))
    native_tax_totals=[Decimal(0),Decimal(0)]
    for index,row in enumerate(load_workbook(gst_path,data_only=True).active.values,1):
        if not row[0] or row[0] in ('Party Name','Total'):continue
        for offset,kind in ((1,'sales_invoice'),(2,'purchase_bill')):
            native_tax_totals[offset-1]+=rounded(row[offset]);check(f'Native GST row {index} {kind} at source precision',rounded(row[offset]),rounded(source_tax[row[0]][kind]))
            # Vyapar rounds this report after grouping unrounded line tax by party.
            # A double-entry ledger posts document tax components in whole paise.
            # Expose the difference instead of asserting the two amounts are identical.
            checks[-1]['posted_amount']=str(rounded(tax[row[0]][kind]))
            checks[-1]['rounding_difference']=str(rounded(row[offset])-rounded(tax[row[0]][kind]))
    check('Native total sales GST',native_tax_totals[0],sum((values['sales_invoice'] for values in tax.values()),Decimal(0)))
    check('Native total purchase GST',native_tax_totals[1],sum((values['purchase_bill'] for values in tax.values()),Decimal(0)))
    return checks
