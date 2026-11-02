"""Narrow source-evidenced financial events; unknown adjustment signs fail closed.

Loan opening header + type-40 transaction are one disbursement, not two.
Type-15 bank adjustment was corroborated by audit paying/receiving accounts.
Numeric adjustment types without directional evidence are deliberately rejected.
"""
from vyapar_audit import decimal as D, rounded as M
from datetime import date

def financial_events(tables, channels):
    events=[];errors=[]
    cash=[key for key,row in channels.items() if row.get('paymentType_type')=='CASH']
    def issued(value):return date.fromisoformat(str(value)[:10]).isoformat()
    for row in tables.get('kb_cash_adjustments',[]):
        errors.append(f"Cash adjustment {row.get('cash_adj_id')} type {row.get('cash_adj_type')}: direction requires native cash-book evidence")
    for row in tables.get('kb_bank_adjustments',[]):
        sid=row.get('bank_adj_id');source=row.get('bank_adj_bank_id');target=row.get('bank_adj_to_bank_id')
        if row.get('bank_adj_type')!=15 or target is not None or len(cash)!=1 or channels.get(source,{}).get('paymentType_type')!='BANK' or M(row.get('bank_adj_amount'))<=0:
            errors.append(f"Bank adjustment {sid} type {row.get('bank_adj_type')}: direction requires native bank-statement evidence");continue
        try:day=issued(row.get('bank_adj_date'))
        except ValueError:errors.append(f'Bank adjustment {sid}: invalid date');continue
        events.append({'kind':'bank_transfer','source_id':sid,'source_table':'kb_bank_adjustments','date':day,'amount':str(M(row['bank_adj_amount'])),'debit_channel':cash[0],'credit_channel':source,'original':row})
    loans={r['loan_account_id']:r for r in tables.get('loan_accounts',[])}
    transactions=tables.get('loan_transactions',[])
    for key,loan in loans.items():
        rows=[r for r in transactions if r.get('loan_account_id')==key]
        if len(rows)!=1:
            errors.append(f'Loan {key}: expected one verified paired opening disbursement');continue
        row=rows[0];channel=row.get('payment_acc_id');principal=M(row.get('principal_amount'))
        if row.get('loan_txn_type')!=40 or loan.get('loan_account_type')!=0 or principal<=0 or principal!=M(loan.get('opening_bal')) or D(row.get('interest_amount')) or str(row.get('txn_date'))[:10]!=str(loan.get('opening_date'))[:10] or channels.get(channel,{}).get('paymentType_type') not in ('CASH','BANK'):
            errors.append(f'Loan {key}: unverified loan transaction or opening mismatch');continue
        try:day=issued(row.get('txn_date'))
        except ValueError:errors.append(f'Loan {key}: invalid opening date');continue
        events.append({'kind':'loan_opening','source_id':row['loan_txn_id'],'source_table':'loan_transactions','loan_id':key,'loan_name':loan.get('loan_account_name') or 'Source loan','date':day,'amount':str(principal),'debit_channel':channel,'original':row,'source_loan':loan})
    for row in transactions:
        if row.get('loan_account_id') not in loans:errors.append('Loan transaction references missing loan account')
    return events,errors
