"""Read-only reconciliation of a company JSON downloaded through the hosted UI."""
import argparse,json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from reconcile_vyapar_native import reconcile

def verify(payload,transactions,stock,gst):
    records=[r for r in payload['records'] if r['kind']!='vyapar_backup_archive']
    posted={p['record_id'] for p in payload['record_postings']};conversions={p['source_record_id']:p['target_record_id'] for p in payload['document_conversions']}
    allocations=defaultdict(Decimal)
    for allocation in payload['payment_allocations']:allocations[allocation['document_id']]+=Decimal(allocation['amount'])
    for record in records:
        record['posted']=record['id'] in posted
        record['converted_to']=conversions.get(record['id']) or ('source-converted' if record['data'].get('vyapar_converted') else None)
        record['outstanding']=str(Decimal(record['amount'])-allocations[record['id']])
    movements=defaultdict(lambda:[Decimal(0),Decimal(0)])
    for movement in payload['stock_movements']:
        movements[movement['item_id']][0]+=Decimal(movement['quantity']);movements[movement['item_id']][1]+=Decimal(movement['cost_value'])
    stock_report={'rows':[{'name':r['name'],'closing_quantity':str(movements[r['id']][0]),'closing_value':str(movements[r['id']][1])} for r in records if r['kind']=='item']}
    checks=reconcile(records,stock_report,transactions,stock,gst)
    balances=defaultdict(Decimal);journal_balances=defaultdict(Decimal)
    for line in payload['journal_lines']:
        movement=Decimal(line['debit'])-Decimal(line['credit']);balances[line['account_id']]+=movement;journal_balances[line['journal_id']]+=movement
    checks += [{'check':'Hosted journal '+str(index)+' balances','expected':'0','actual':str(journal_balances[journal['id']]),'passed':journal_balances[journal['id']]==0} for index,journal in enumerate(payload['journals'],1)]
    return {'company':payload['company'],'exported_at':payload['exported_at'],'record_count':len(records),'journals':len(payload['journals']),
        'allocations':len(payload['payment_allocations']),'conversions':len(payload['document_conversions']),'stock_movements':len(payload['stock_movements']),
        'accounts':[{'code':a['code'],'name':a['name'],'balance':str(balances[a['id']])} for a in payload['accounts']],
        'checks':checks,'passed':all(c['passed'] for c in checks)}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('company_export');p.add_argument('transactions');p.add_argument('stock');p.add_argument('gst');p.add_argument('--output',required=True);a=p.parse_args()
    result=verify(json.loads(Path(a.company_export).read_text(encoding='utf-8-sig')),a.transactions,a.stock,a.gst)
    Path(a.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'company':result['company']['name'],'passed':result['passed'],'checks':len(result['checks']),'journals':result['journals'],'records':result['record_count'],'failed':[c for c in result['checks'] if not c['passed']]},indent=2))
    if not result['passed']:raise SystemExit(1)
