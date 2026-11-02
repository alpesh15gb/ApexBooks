"""Compare every visible source transaction with a native Vyapar XLSX report."""
import argparse
import base64
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from openpyxl import load_workbook
from vyapar_import import inspect_backup
from vyapar_audit import transaction_audit, rounded

def run(backup_path, native_path, output):
    backup=inspect_backup(base64.b64encode(Path(backup_path).read_bytes()).decode())
    audit=transaction_audit(backup['tables'])
    native=defaultdict(list)
    for values in load_workbook(native_path,data_only=True).active.values:
        if len(values)<10 or not isinstance(values[0],str): continue
        try: date=datetime.strptime(values[0],'%d/%m/%Y').date().isoformat()
        except ValueError: continue
        identity=(date,str(values[1] or ''),str(values[2] or ''),str(values[4] or '').strip())
        native[identity].append(values)
    for row in audit['rows']:
        identity=(row['date'],row['reference'],row['party'],row['source_type_name'])
        matches=native.get(identity,[])
        if row['converted']:
            row['native_report_status']='excluded_converted_estimate' if not matches else 'unexpected_converted_row'
        elif len(matches)!=1: row['native_report_status']='missing_or_ambiguous'
        else:
            actual=matches[0]; issues=[]
            if rounded(actual[5])!=rounded(row['amount']): issues.append('amount')
            # Native Purchase Orders may display Paid, but they do not post a purchase.
            paid=actual[7] if row['source_type'] in {2,28} else actual[8]
            expected_paid=rounded(row['paid_at_document']) + (rounded(row['linked_amount']) if row['source_type']==1 else 0)
            if rounded(paid)!=expected_paid: issues.append('paid_received')
            if row['source_type']==1 and rounded(actual[9])!=rounded(row['derived_invoice_outstanding']): issues.append('outstanding')
            row['native_report_status']='match' if not issues else 'mismatch_'+','.join(issues)
            native.pop(identity)
    audit['native_comparison']={'matched':sum(r['native_report_status']=='match' for r in audit['rows']),
        'converted_excluded':sum(r['native_report_status']=='excluded_converted_estimate' for r in audit['rows']),
        'mismatched_or_missing':sum(r['native_report_status'] not in {'match','excluded_converted_estimate'} for r in audit['rows']),
        'unmatched_native_rows':sum(len(rows) for rows in native.values())}
    audit['backup_digest']=backup['digest']
    output=Path(output)
    output.with_suffix('.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
    report=['# Apex Integrations transaction mapping audit','',
        'Compared the supplied backup with the All Transactions XLSX exported from the open Vyapar desktop company.',
        '', '**Source-only audit.** This report does not inspect a target company. Use its posting reconciliation and the separate posting verification report for evidence of committed journals.',
        '', '## Native reconciliation', '', json.dumps(audit['native_comparison']), '',
        '## Source totals', '', *[f'- {key}: INR {value}' for key,value in audit['totals'].items()], '',
        '## Mapping requirements', '',
        '- Preserve conversion links, unit conversions, prefixes, tax mappings and opening account data. The previous archive selected only 11 source tables and omitted conversion links.',
        '- Use line tax details, inclusive/exclusive pricing codes, discounts, extra charges and source round-off. Transaction-level tax is zero in this backup despite line tax.',
        '- Keep estimates and orders outside sales, purchases and stock. Post purchase-order payments separately as supplier advances. Retain converted estimate status.',
        '- Post paid-at-invoice amounts and standalone receipts separately and use payment mappings to select the correct bank/cash accounts.',
        '- Preserve receipt allocations as dated links. One converted estimate has no source destination link and needs review.',
        '- Reconcile source openings, receivables, bank balances and inventory before any live historical migration.',
        '', '## Every source transaction', '',
        '| Source ID | Source type | Reference | Amount INR | Native report | Source checks | Live ledger |',
        '|---|---|---|---:|---|---|---|']
    for row in audit['rows']:
        report.append('| '+ ' | '.join(str(value).replace('|','/') for value in [row['source_id'],row['source_type_name'],row['reference'],row['amount'],row['native_report_status'], '; '.join(row['issues']) or 'Passed',row['live_ledger_status']])+' |')
    output.with_suffix('.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    return audit

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('backup');parser.add_argument('native_xlsx');parser.add_argument('--output',required=True)
    args=parser.parse_args();result=run(args.backup,args.native_xlsx,args.output)
    print(json.dumps({key:result[key] for key in ('native_comparison','totals','review_required_count','global_issues')},indent=2))
