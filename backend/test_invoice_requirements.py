"""Synthetic minimum statutory invoice guards; never contacts a tax portal."""
import unittest
from datetime import date
from uuid import uuid4
from fastapi import HTTPException
from invoice_requirements import validate_outward_invoice_fields
import test_api
import test_completion


class InvoiceRequirementsTest(unittest.TestCase):
    def context(self):
        return test_completion.CompletionTest.client_context(self, 'regular')

    def invoice(self, client, headers, base, **data):
        payload = {'kind': 'sales_invoice', 'name': 'Synthetic buyer', 'date': '2026-11-12',
                   'data': {'place_of_supply': '36', 'lines': [{'description': 'Synthetic service',
                   'quantity': 1, 'rate': 100, 'gst_rate': 18, 'hsn': '9983'}], **data}}
        return client.post(base + '/records', headers=headers, json=payload), payload

    def test_b2b_blank_hsn_rejected_without_posting(self):
        c,h,b = self.context()
        before = c.get(b+'/journals', headers=h).json()
        r,_ = self.invoice(c,h,b,party_gstin='36ABCDE1234F1Z5',lines=[{'description':'Service','quantity':1,'rate':100,'gst_rate':18,'hsn':''}])
        self.assertEqual(r.status_code,422,r.text)
        self.assertIn('HSN/SAC',r.text)
        self.assertEqual(c.get(b+'/journals',headers=h).json(),before)

    def test_b2c_taxable_threshold_and_address(self):
        c,h,b = self.context()
        line={'description':'Service','quantity':1,'rate':'49999.99','gst_rate':18,'hsn':''}
        r,_=self.invoice(c,h,b,lines=[line]);self.assertEqual(r.status_code,200,r.text)
        line['rate']='50000'
        r,_=self.invoice(c,h,b,lines=[line]);self.assertEqual(r.status_code,422,r.text)
        r,_=self.invoice(c,h,b,lines=[line],party_address='Synthetic buyer, Hyderabad, Telangana 500001')
        self.assertEqual(r.status_code,200,r.text)

    def test_header_amendment_cannot_remove_hsn(self):
        c,h,b=self.context()
        r,p=self.invoice(c,h,b,party_gstin='36ABCDE1234F1Z5');self.assertEqual(r.status_code,200,r.text)
        doc=r.json();p['number']=doc['number'];p['data']['version']=0;p['data']['lines'][0]['hsn']=''
        r=c.put(b+'/documents/'+doc['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=p)
        self.assertEqual(r.status_code,422,r.text)
        saved=c.get(b+'/records',headers=h,params={'kind':'sales_invoice'}).json()[0]
        self.assertEqual(saved['data']['lines'][0]['hsn'],'9983')

    def test_header_amendment_cannot_remove_required_address(self):
        c,h,b=self.context()
        r,p=self.invoice(c,h,b,party_address='Hyderabad, Telangana',lines=[{'description':'Service','quantity':1,'rate':50000,'gst_rate':18,'hsn':'9983'}])
        self.assertEqual(r.status_code,200,r.text)
        doc=r.json();p['number']=doc['number'];p['data']['version']=0;p['data']['party_address']=''
        r=c.put(b+'/documents/'+doc['id'],headers={**h,'Idempotency-Key':uuid4().hex},json=p)
        self.assertEqual(r.status_code,422,r.text)

    def test_scope_does_not_infer_turnover_or_rewrite_history(self):
        data={'party_gstin':'36ABCDE1234F1Z5','lines':[{'hsn':''}],'taxable_supply_value':'100'}
        for kind,mode,day in [('purchase_bill','regular',date(2026,11,12)),('sales_invoice','unregistered',date(2026,11,12)),('estimate','regular',date(2026,11,12)),('sales_invoice','regular',date(2020,11,12))]:
            validate_outward_invoice_fields(kind,mode,data,day)
        validate_outward_invoice_fields('sales_invoice','regular',{**data,'party_gstin':''},date(2026,11,12))
        validate_outward_invoice_fields('sales_invoice','regular',{**data,'document_tax_form':'bill_of_supply'},date(2026,11,12))
