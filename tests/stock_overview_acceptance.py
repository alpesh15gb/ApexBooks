"""Real synthetic API responses rendered by the production React overview; no browser/device claim."""
import json,os,subprocess,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
# Never inherit an external API target for this isolated cross-stack test.
os.environ.pop('ACCEPTANCE_BASE',None)
sys.path.insert(0,str(ROOT/'backend'))
import test_completion
class StockOverviewAcceptance(unittest.TestCase):
 def test_actual_opening_increase_and_decrease_responses(self):
  c,h,b=test_completion.CompletionTest.client_context(self)
  item=c.post(b+'/records',headers=h,json={'kind':'item','name':'Synthetic stock','data':{'track_stock':True,'unit':'pcs'}});item.raise_for_status()
  rows=[]
  for path,body in [('/stock/opening',{'quantity':10,'unit_cost':80}),('/stock/adjustments',{'direction':'increase','quantity':2,'unit_cost':80,'reason':'Counted extra'}),('/stock/adjustments',{'direction':'decrease','quantity':5,'reason':'Damaged'})]:
   result=c.post(b+path,headers=h,json={'item_id':item.json()['id'],'date':'2026-04-01',**body});self.assertEqual(result.status_code,201,result.text)
   detail=c.get(b+'/records/'+result.json()['id'],headers=h);detail.raise_for_status();rows.append(detail.json())
  run=subprocess.run(['node','tests/renderStockOverview.mjs'],cwd=ROOT/'frontend',input=json.dumps(rows),text=True,capture_output=True,check=True)
  opening,increase,decrease=json.loads(run.stdout)
  self.assertIn('10 pcs',opening);self.assertIn('₹80.00',opening)
  self.assertIn('+2 pcs',increase);self.assertIn('Stock value introduced',increase);self.assertIn('₹160.00',increase)
  self.assertIn('−5 pcs',decrease);self.assertIn('Stock value removed',decrease);self.assertIn('₹400.00',decrease);self.assertIn('Not separately recorded',decrease)
  for markup in (opening,increase,decrease):self.assertNotIn('Payment &amp; document trail',markup)
if __name__=='__main__':unittest.main()
