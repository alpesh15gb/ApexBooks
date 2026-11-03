"""Synthetic API regressions for non-GST cost mapping and source-only openings."""
import unittest
from decimal import Decimal

import test_vyapar_expanded as expanded
from test_vyapar_posting import fixture, encode
from vyapar_posting import posting_plan


def empty_books():
    tables=fixture()
    for name in ('kb_transactions','kb_lineitems','txn_payment_mapping','kb_txn_links','kb_linked_transactions'):
        tables[name]=[]
    for row in tables['kb_names']:row['amount']=0
    for row in tables['kb_items']:row.update(item_stock_quantity=0,item_stock_value=0)
    return tables


def purchase_books(*, sale_date=None, inclusive_source=False):
    original=fixture();tables=empty_books()
    tables['kb_firms'][0]['firm_gstin_number']=''
    tables['kb_transactions']=[original['kb_transactions'][1]]
    tables['kb_lineitems']=[original['kb_lineitems'][1]]
    tables['txn_payment_mapping']=[original['txn_payment_mapping'][1]]
    tables['kb_items'][1].update(item_stock_quantity=3,item_stock_value=177 if inclusive_source else 150)
    if sale_date:
        sale=original['kb_transactions'][0]
        sale.update(txn_cash_amount=0,txn_balance_amount=200,txn_date=sale_date)
        line=original['kb_lineitems'][0]
        line.update(item_id=2,total_amount=200,lineitem_tax_amount=0,lineitem_tax_id=None,priceperunit=100)
        tables['kb_transactions'].append(sale);tables['kb_lineitems'].append(line)
        tables['kb_names'][0]['amount']=200
        tables['kb_items'][1].update(item_stock_quantity=1,item_stock_value=59 if inclusive_source else 50)
    return tables


class VyaparTaxAndOpeningTests(unittest.TestCase):
    client=expanded.ExpandedVyaparTests.client
    post=expanded.ExpandedVyaparTests.post
    roundtrip=expanded.ExpandedVyaparTests.roundtrip

    def ledger(self,c,h,b):
        exported=c.get(b+'/data-export.json',headers=h).json()
        codes={row['id']:row['code'] for row in exported['accounts']}
        totals={code:Decimal(0) for code in codes.values()}
        for row in exported['journal_lines']:
            totals[codes[row['account_id']]]+=Decimal(row['debit'])-Decimal(row['credit'])
        return totals

    def assert_no_input_tax(self,c,h,b,records):
        bill=next(row for row in records if row['kind']=='purchase_bill')
        self.assertEqual(bill['data']['tax_mode'],'unregistered')
        self.assertEqual(Decimal(bill['data']['input_tax_ineligible']),27)
        for key in ('cgst','sgst','igst'):
            self.assertEqual(Decimal(bill['data']['pending_input_'+key]),0)
            self.assertEqual(self.ledger(c,h,b)['SYS-IN-'+key.upper()],0)
        self.assertTrue(all(line['itc_treatment']=='ineligible' for line in bill['data']['lines']))

    def test_non_gst_purchase_matches_normal_cost_and_preserves_source_bridge(self):
        for inclusive in (False,True):
            with self.subTest(source_tax_inclusive=inclusive):
                tables=purchase_books(inclusive_source=inclusive)
                c,h,b,records=self.post(tables)
                self.assert_no_input_tax(c,h,b,records)
                self.assertEqual(self.ledger(c,h,b)['SYS-INVENTORY'],177)
                stock=next(row for row in self.posting_result['stock_valuation_reconciliation'] if row['source_item_id']==2)
                self.assertEqual(Decimal(stock['source_value']),177 if inclusive else 150)
                self.assertEqual(Decimal(stock['nonrecoverable_tax_adjustment']),0 if inclusive else 27)
                self.assertEqual(Decimal(stock['source_value'])+Decimal(stock['source_rounding_adjustment'])+Decimal(stock['nonrecoverable_tax_adjustment']),177)
                self.assertEqual(Decimal(self.posting_result['nonrecoverable_supplier_tax']),27)
                self.assertTrue(all(row['passed'] for row in self.posting_result['reconciliation']))
                if not inclusive:self.assertTrue(any('nonrecoverable supplier GST 27.00' in warning for warning in self.posting_result['warnings']))
                exported=self.roundtrip(c,h,b)
                archive=next(row for row in exported['records'] if row['kind']=='vyapar_backup_archive')
                self.assertEqual(Decimal(archive['data']['tables']['kb_items'][1]['item_stock_value']),177 if inclusive else 150)
                before=len(records)
                payload={'backup_base64':encode(tables),'digest':self.posting_result['digest']}
                replay=c.post(b+'/imports/vyapar-posting/commit',headers=h,json=payload)
                self.assertEqual(replay.status_code,200,replay.text);self.assertTrue(replay.json()['already_imported'])
                self.assertEqual(len(c.get(b+'/records',headers=h).json()),before)
        # Control uses the ordinary posting route, independently of the importer.
        c,h,b=self.client()
        item=c.post(b+'/records',headers=h,json={'kind':'item','name':'Normal cost item','data':{'track_stock':True,'item_type':'goods','purchase_rate':'50','gst_rate':'18'}})
        self.assertEqual(item.status_code,200,item.text)
        normal=c.post(b+'/records',headers=h,json={'kind':'purchase_bill','name':'Normal supplier','date':'2026-04-01','data':{'supplier_state':'36','place_of_supply':'36','lines':[{'item_id':item.json()['id'],'description':'Normal cost item','quantity':'3','rate':'50','gst_rate':'18'}]}})
        self.assertEqual(normal.status_code,200,normal.text)
        self.assertEqual(Decimal(normal.json()['amount']),177)
        self.assertEqual(self.ledger(c,h,b)['SYS-INVENTORY'],177)
        self.assertEqual(Decimal(normal.json()['data']['pending_input_cgst']),0)

    def test_non_gst_fifo_and_legacy_shortage_allocate_nonrecoverable_tax(self):
        for sale_date in ('2026-03-31','2026-04-02'):
            with self.subTest(sale_date=sale_date):
                c,h,b,records=self.post(purchase_books(sale_date=sale_date))
                self.assert_no_input_tax(c,h,b,records)
                balances=self.ledger(c,h,b)
                self.assertEqual(balances['SYS-INVENTORY'],59)
                self.assertEqual(balances['SYS-COGS'],118)
                self.assertEqual(balances['SYS-SALES'],-200)
                self.assertTrue(all(row['passed'] for row in self.posting_result['reconciliation']))
                self.roundtrip(c,h,b)

    def test_fractional_source_lines_allocate_nonnegative_paise_and_exact_totals(self):
        for regular in (False,True):
            with self.subTest(regular=regular):
                tables=purchase_books()
                if regular:tables['kb_firms'][0]['firm_gstin_number']=fixture()['kb_firms'][0]['firm_gstin_number']
                template=tables['kb_lineitems'][0]
                base=Decimal('.0333');tax=base*Decimal('.18');gross=base+tax
                tables['kb_lineitems']=[{**template,'lineitem_id':index,'quantity':1,'total_amount':str(gross),'lineitem_tax_amount':str(tax),'priceperunit':str(gross)} for index in range(1,100)]
                tables['kb_transactions'][0]['txn_cash_amount']='3.89'
                tables['txn_payment_mapping'][0]['amount']='3.89'
                tables['kb_items'][1].update(item_stock_quantity=99,item_stock_value='3.30')
                plan=posting_plan(tables)
                self.assertTrue(plan['ready'],plan['errors'])
                self.assertEqual(plan,posting_plan(tables))
                document=plan['documents'][0]
                self.assertTrue(all(Decimal(line[field])>=0 for line in document['lines'] for field in ('taxable','tax','inventory_cost')))
                self.assertEqual(sum(Decimal(line['taxable']) for line in document['lines']),Decimal('3.30'))
                self.assertEqual(sum(Decimal(line['tax']) for line in document['lines']),Decimal('.59'))
                self.assertEqual(sum(Decimal(value) for value in document['taxes'].values()),Decimal('.59'))
                self.assertEqual(sum(Decimal(line['source_tax']) for line in document['lines']),tax*99)
                c,h,b,records=self.post(tables)
                self.assertTrue(all(row['passed'] for row in self.posting_result['reconciliation']))
                balances=self.ledger(c,h,b)
                self.assertEqual(balances['SYS-INVENTORY'],Decimal('3.30') if regular else Decimal('3.89'))
                self.assertEqual(balances['SYS-IN-CGST']+balances['SYS-IN-SGST'],Decimal('.59') if regular else 0)
                self.assertEqual(balances['VYP-ROUND'],0)
                self.roundtrip(c,h,b)

    def test_normal_sale_and_supplier_return_continue_with_imported_gross_cost(self):
        c,h,b,records=self.post(purchase_books())
        item=next(row for row in records if row['kind']=='item' and row['data']['vyapar_source_id']==2)
        bill=next(row for row in records if row['kind']=='purchase_bill')
        base_line={'item_id':item['id'],'description':item['name'],'quantity':'1','rate':'100','gst_rate':'0','tax_treatment':'non_gst'}
        sale=c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':'Later buyer','date':'2026-04-02','data':{'lines':[base_line]}})
        self.assertEqual(sale.status_code,200,sale.text)
        self.assertEqual(Decimal(sale.json()['data']['lines'][0]['inventory_cost']),59)
        returned=c.post(b+'/records',headers=h,json={'kind':'debit_note','name':bill['name'],'date':'2026-04-03','data':{
            'applied_to':bill['id'],'party_id':bill['data']['party_id'],'supplier_state':'36','place_of_supply':'36',
            'lines':[{**base_line,'rate':'50','gst_rate':'18','tax_treatment':'taxable'}]}})
        self.assertEqual(returned.status_code,200,returned.text)
        self.assertEqual(Decimal(returned.json()['amount']),59)
        self.assertEqual(Decimal(returned.json()['data']['pending_input_cgst']),0)
        balances=self.ledger(c,h,b)
        self.assertEqual(balances['SYS-INVENTORY'],59)
        self.assertEqual(balances['SYS-COGS'],59)
        self.assertEqual(balances['SYS-IN-CGST'],0)
        self.assertEqual(balances['SYS-IN-SGST'],0)
        self.roundtrip(c,h,b)

    def test_non_gst_unsupported_tax_or_source_cost_remains_atomic(self):
        for reason in ('stock','outward_tax'):
            with self.subTest(reason=reason):
                tables=purchase_books(sale_date='2026-04-02')
                if reason=='stock':tables['kb_items'][1]['item_stock_value']=73
                else:
                    tables['kb_transactions'][1]['txn_balance_amount']=236
                    tables['kb_names'][0]['amount']=236
                    tables['kb_lineitems'][1].update(total_amount=236,lineitem_tax_amount=36,lineitem_tax_id=24)
                c,h,b=self.client();payload={'backup_base64':encode(tables)}
                preview=c.post(b+'/imports/vyapar-posting/preview',headers=h,json=payload)
                self.assertEqual(preview.status_code,200,preview.text);self.assertFalse(preview.json()['ready'])
                self.assertTrue(any(('cost reconstruction' if reason=='stock' else 'outward GST') in error for error in preview.json()['errors']))
                payload['digest']=preview.json()['digest']
                commit=c.post(b+'/imports/vyapar-posting/commit',headers=h,json=payload)
                self.assertEqual(commit.status_code,422,commit.text)
                self.assertEqual(c.get(b+'/records',headers=h).json(),[])

    def test_opening_only_and_master_only_cutoff_replay_and_restore(self):
        for amount in (Decimal('500'),Decimal('-500'),Decimal(0)):
            with self.subTest(opening_amount=amount):
                tables=empty_books()
                if amount:tables['kb_paymentTypes'][1].update(paymentType_opening_balance=str(amount),paymentType_opening_date='2026-04-12')
                c,h,b,records=self.post(tables)
                self.assertEqual(self.posting_result['source_as_of'],'2026-04-12' if amount else None)
                self.assertEqual(self.posting_result['journals_posted'],1 if amount else 0)
                self.assertEqual(self.ledger(c,h,b)['VYP-BANK-3'],amount)
                self.assertTrue(all(row['passed'] for row in self.posting_result['reconciliation']))
                self.roundtrip(c,h,b)
                payload={'backup_base64':encode(tables),'digest':self.posting_result['digest']}
                replay=c.post(b+'/imports/vyapar-posting/commit',headers=h,json=payload)
                self.assertEqual(replay.status_code,200,replay.text);self.assertTrue(replay.json()['already_imported'])
                self.assertEqual(replay.json()['source_as_of'],self.posting_result['source_as_of'])
                self.assertEqual(len(c.get(b+'/records',headers=h).json()),len(records))

    def test_cutoff_includes_later_stock_bank_and_loan_events(self):
        for category in ('stock','bank','loan'):
            with self.subTest(category=category):
                tables=fixture()
                if category=='stock':
                    tables['kb_items'][0]['item_stock_quantity']=0
                    tables['kb_item_adjustments']=[{'item_adj_id':1,'item_adj_item_id':1,'item_adj_type':11,'item_adj_quantity':2,'item_adj_atprice':-1,'item_adj_date':'2026-06-03'}]
                elif category=='bank':
                    tables['kb_bank_adjustments']=[{'bank_adj_id':1,'bank_adj_bank_id':3,'bank_adj_type':15,'bank_adj_amount':50,'bank_adj_date':'2026-06-03','bank_adj_to_bank_id':None}]
                else:
                    tables['loan_accounts']=[{'loan_account_id':1,'loan_account_name':'Synthetic late loan','loan_account_type':0,'opening_bal':2500,'opening_date':'2026-06-03'}]
                    tables['loan_transactions']=[{'loan_txn_id':1,'loan_account_id':1,'loan_txn_type':40,'principal_amount':2500,'interest_amount':0,'payment_acc_id':1,'txn_date':'2026-06-03'}]
                self.post(tables)
                self.assertEqual(self.posting_result['source_as_of'],'2026-06-03')


if __name__=='__main__':unittest.main()
