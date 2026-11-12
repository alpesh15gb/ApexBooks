import unittest
from decimal import Decimal
import test_completion

class DocumentDiscountMessageTest(unittest.TestCase):
 def test_invalid_document_discount_preview_and_create_are_actionable_and_atomic(self):
  c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
  initial=c.get(b+'/records',headers=h).json()
  for value in ['101','-1','NaN','Infinity','1.001','bad',None]:
   body={'kind':'sales_invoice','name':'Synthetic discount buyer','date':'2026-04-01','data':{'document_discount_percent':value,'lines':[{'description':'Goods','quantity':1,'rate':'100','gst_rate':0}]}}
   for endpoint in ['/documents/preview','/records']:
    with self.subTest(value=value,endpoint=endpoint):
     response=c.post(b+endpoint,headers=h,json=body)
     self.assertEqual(response.status_code,422,response.text)
     self.assertEqual(response.json()['detail'],'Document discount must be between 0 and 100 percent with at most two decimal places')
  self.assertEqual(c.get(b+'/records',headers=h).json(),initial)
  for value in ['0','12.34','99.99']:
   body['data']['document_discount_percent']=value
   preview=c.post(b+'/documents/preview',headers=h,json=body);preview.raise_for_status()
   saved=c.post(b+'/records',headers=h,json=body);saved.raise_for_status()
   self.assertEqual(Decimal(str(preview.json()['amount'])),Decimal(str(saved.json()['amount'])))
  body['data']['document_discount_percent']='100'
  preview=c.post(b+'/documents/preview',headers=h,json=body);preview.raise_for_status();self.assertEqual(Decimal(str(preview.json()['amount'])),Decimal('0'))
