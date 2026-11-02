"""Sales orders preserve source lineage without posting stock or accounts."""
import io
import unittest
from decimal import Decimal
from uuid import uuid4
from pypdf import PdfReader
import test_api
import test_completion

class SalesOrderTest(unittest.TestCase):
    def context(self):return test_completion.CompletionTest.client_context(self)

    def test_estimate_order_invoice_chain_posts_only_final_invoice(self):
        client,h,base=self.context()
        payload={'name':'Synthetic buyer','date':'2026-04-02','data':{'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}}
        def post(kind,source=None):
            r=client.post(base+'/records',headers={**h,'Idempotency-Key':uuid4().hex},json={**payload,'kind':kind,'data':{**payload['data'],**({'source_document_id':source} if source else {})}})
            self.assertEqual(r.status_code,200,r.text);return r.json()
        estimate=post('estimate')
        order=post('sales_order',estimate['id'])
        self.assertFalse(order['posted']);self.assertTrue(order['number'].startswith('SO'))
        self.assertEqual(client.get(base+'/journals',headers=h).json(),[])
        amendment=client.put(base+'/drafts/'+order['id'],headers=h,json={**payload,'kind':'sales_order','number':order['number'],'data':{**payload['data'],'source_document_id':'forged-source','vyapar_converted':True,'version':0}})
        self.assertEqual(amendment.status_code,200,amendment.text)
        self.assertEqual(amendment.json()['data']['source_document_id'],estimate['id'])
        self.assertNotIn('vyapar_converted',amendment.json()['data'])
        for template in ('classic','modern'):
            pdf=client.get(base+'/documents/'+order['id']+'.pdf',headers=h,params={'template':template})
            self.assertEqual(pdf.status_code,200,pdf.text[:100] if pdf.status_code!=200 else '')
            text=' '.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
            self.assertIn('sales order',text.lower())
        invoice=post('sales_invoice',order['id'])
        self.assertTrue(invoice['posted'])
        self.assertEqual(len(client.get(base+'/journals',headers=h).json()),1)
        rows={r['id']:r for r in client.get(base+'/records',headers=h).json()}
        self.assertEqual(rows[estimate['id']]['converted_to'],order['id'])
        self.assertEqual(rows[order['id']]['converted_to'],invoice['id'])
        for kind,source in (('sales_order',estimate['id']),('sales_invoice',order['id'])):
            r=client.post(base+'/records',headers=h,json={**payload,'kind':kind,'data':{**payload['data'],'source_document_id':source}})
            self.assertEqual(r.status_code,409,r.text)
        r=client.put(base+'/drafts/'+order['id'],headers=h,json={**payload,'kind':'sales_order','number':order['number']})
        self.assertEqual(r.status_code,409,r.text)

    def test_sales_order_can_be_edited_without_posting_or_reserving_stock(self):
        client,h,base=self.context()
        item=client.post(base+'/records',headers=h,json={'kind':'item','name':'Synthetic tracked item','data':{'track_stock':True}}).json()
        payload={'kind':'sales_order','name':'Buyer','date':'2026-04-02','data':{'lines':[{'item_id':item['id'],'description':item['name'],'quantity':2,'rate':100,'gst_rate':0}]}}
        order=client.post(base+'/records',headers=h,json=payload)
        self.assertEqual(order.status_code,200,order.text);order=order.json()
        amended=client.put(base+'/drafts/'+order['id'],headers=h,json={**payload,'number':order['number'],'data':{**payload['data'],'notes':'Reviewed','version':0}})
        self.assertEqual(amended.status_code,200,amended.text)
        self.assertFalse(amended.json()['posted'])
        self.assertEqual(client.get(base+'/journals',headers=h).json(),[])
        stock=client.get(base+'/reports/stock',headers=h,params={'from_date':'2026-04-01','to_date':'2026-04-30'}).json()
        self.assertTrue(all(Decimal(row['closing_quantity'])==0 for row in stock['rows']))
        stale=client.put(base+'/drafts/'+order['id'],headers=h,json={**payload,'number':order['number'],'data':{**payload['data'],'version':0}})
        self.assertEqual(stale.status_code,409,stale.text)

    def test_conversion_requires_same_party_and_nonretroactive_date(self):
        client,h,base=self.context()
        payload={'kind':'proforma','name':'Buyer','date':'2026-04-02','data':{'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}}
        source=client.post(base+'/records',headers=h,json=payload).json()
        for change in ({'name':'Other party'},{'date':'2026-04-01'}):
            r=client.post(base+'/records',headers=h,json={**payload,'kind':'sales_order',**change,'data':{**payload['data'],'source_document_id':source['id']}})
            self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(client.get(base+'/journals',headers=h).json(),[])

    def test_party_statement_marks_sales_order_lifecycle_consistently(self):
        client,h,base=self.context()
        party=client.post(base+'/records',headers=h,json={'kind':'party','name':'Statement buyer'}).json()
        payload={'kind':'sales_order','name':party['name'],'date':'2026-04-02','data':{'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}}
        order=client.post(base+'/records',headers=h,json=payload).json()
        path=base+'/parties/'+party['id']+'/statement'
        query={'from_date':'2026-04-01','to_date':'2026-04-30'}
        before=client.get(path,headers=h,params=query).json()['transactions'][0]
        self.assertTrue(before['editable']);self.assertIsNone(before['converted_to'])
        invoice=client.post(base+'/records',headers=h,json={**payload,'kind':'sales_invoice','data':{**payload['data'],'source_document_id':order['id']}}).json()
        after=next(r for r in client.get(path,headers=h,params=query).json()['transactions'] if r['id']==order['id'])
        self.assertFalse(after['editable']);self.assertEqual(after['converted_to'],invoice['id'])
