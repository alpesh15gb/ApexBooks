import unittest
import test_completion
from main import engine,Record
from sqlalchemy.orm import Session

class ServiceStockBoundaryTest(unittest.TestCase):
 def context(self):return test_completion.CompletionTest.client_context(self,'unregistered')
 def test_new_tracked_service_is_rejected_and_untracked_service_allowed(self):
  c,h,b=self.context();body={'kind':'item','name':'Synthetic installation','data':{'item_type':'services','track_stock':True}}
  response=c.post(b+'/records',headers=h,json=body);self.assertEqual(response.status_code,422,response.text)
  body['data']['track_stock']=False;c.post(b+'/records',headers=h,json=body).raise_for_status();self.assertEqual(c.get(b+'/journals',headers=h).json(),[])
 def test_import_preview_and_commit_reject_tracked_service(self):
  c,h,b=self.context();body={'kind':'item','rows':[{'name':'Synthetic service import','item_type':'services','track_stock':True}]}
  preview=c.post(b+'/masters/import',headers=h,json={**body,'dry_run':True});preview.raise_for_status();self.assertTrue(preview.json()['errors']);self.assertEqual(preview.json()['ready'],0)
  commit=c.post(b+'/masters/import',headers=h,json={**body,'dry_run':False});self.assertEqual(commit.status_code,422,commit.text)
 def test_tracked_goods_cannot_be_reclassified_as_service_without_history(self):
  c,h,b=self.context();item=c.post(b+'/records',headers=h,json={'kind':'item','name':'Synthetic goods','data':{'track_stock':True}}).json()
  response=c.put(b+'/masters/'+item['id'],headers=h,json={'name':item['name'],'track_stock':True,'item_type':'services'});self.assertEqual(response.status_code,422,response.text)
  self.assertEqual(c.get(b+'/records/'+item['id'],headers=h).json()['data']['item_type'],'goods')
 def test_legacy_service_metadata_is_preserved_but_new_opening_blocked(self):
  c,h,b=self.context();item=c.post(b+'/records',headers=h,json={'kind':'item','name':'Legacy synthetic','data':{'track_stock':True}}).json()
  with Session(engine) as session:
   record=session.get(Record,item['id']);record.data={**record.data,'item_type':'services'};session.commit()
  response=c.put(b+'/masters/'+item['id'],headers=h,json={'name':item['name'],'track_stock':True,'item_type':'services','is_active':False});response.raise_for_status()
  response=c.put(b+'/masters/'+item['id'],headers=h,json={'name':item['name'],'track_stock':True,'item_type':'services','is_active':True});response.raise_for_status()
  opening=c.post(b+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-01','quantity':2,'unit_cost':50});self.assertEqual(opening.status_code,422,opening.text);self.assertEqual(c.get(b+'/journals',headers=h).json(),[])
  c.put(b+'/masters/'+item['id'],headers=h,json={'name':item['name'],'track_stock':True,'item_type':'goods'}).raise_for_status()
  c.post(b+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-01','quantity':2,'unit_cost':50}).raise_for_status()

 def test_legacy_service_stock_history_and_backup_are_not_rewritten(self):
  import base64
  c,h,b=self.context();item=c.post(b+'/records',headers=h,json={'kind':'item','name':'Legacy stock history','data':{'track_stock':True}}).json()
  c.post(b+'/stock/opening',headers=h,json={'item_id':item['id'],'date':'2026-04-01','quantity':2,'unit_cost':50}).raise_for_status()
  with Session(engine) as session:
   record=session.get(Record,item['id']);record.data={**record.data,'item_type':'services'};session.commit()
  before=c.get(b+'/journals',headers=h).json()
  c.put(b+'/masters/'+item['id'],headers=h,json={'name':item['name'],'track_stock':True,'item_type':'services','is_active':False}).raise_for_status()
  correction=c.put(b+'/masters/'+item['id'],headers=h,json={'name':item['name'],'track_stock':True,'item_type':'goods'});self.assertEqual(correction.status_code,422,correction.text)
  self.assertEqual(c.get(b+'/journals',headers=h).json(),before)
  export=c.get(b+'/data-export.json',headers=h);export.raise_for_status();preview=c.post('/api/backups/restore/preview',headers=h,json={'company_name':'Legacy service history restore','backup_base64':base64.b64encode(export.content).decode()});self.assertEqual(preview.status_code,200,preview.text)
