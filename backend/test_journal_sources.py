import unittest
import test_completion
from main import engine, Journal
from sqlalchemy.orm import Session

class JournalSourcesTest(unittest.TestCase):
    def test_posted_cancelled_and_lookalike_sources_are_scoped(self):
        c,h,b=test_completion.CompletionTest.client_context(self)
        row=c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':'Recognizable buyer','date':'2026-04-01','data':{'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}}).json()
        journals=c.get(b+'/journals',headers=h).json()
        linked=[j for j in journals if j['source_record_id']==row['id']]
        self.assertEqual(len(linked),1)
        self.assertEqual(linked[0]['source_document']['number'],row['number'])
        self.assertEqual(linked[0]['source_document']['name'],'Recognizable buyer')
        response=c.post(b+'/records/'+row['id']+'/cancel',headers=h,json={'reason':'Synthetic duplicate'})
        self.assertEqual(response.status_code,200,response.text)
        linked=[j for j in c.get(b+'/journals',headers=h).json() if j['source_record_id']==row['id']]
        self.assertEqual(len(linked),2)
        self.assertTrue(all(j['source_document']['cancelled'] for j in linked))
        other,oh,ob=test_completion.CompletionTest.client_context(self)
        with Session(engine) as session:
            fake=Journal(company_id=ob.split('/')[3],date=__import__('datetime').date(2026,4,1),reference='AUTO:'+row['id'],memo='Synthetic lookalike',created_by=session.get(Journal,linked[0]["id"]).created_by)
            session.add(fake);session.commit()
        visible=other.get(ob+'/journals',headers=oh)
        self.assertEqual(visible.status_code,200,visible.text)
        self.assertTrue(all(j['source_document'] is None for j in visible.json()))
        self.assertNotIn('Recognizable buyer',visible.text)
        self.assertEqual(other.get(b+'/journals',headers=oh).status_code,404)

    def test_cancelled_source_links_survive_repeated_restore(self):
        from test_record_trail import RecordTrailTest
        c,h,b=test_completion.CompletionTest.client_context(self)
        row=c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':'Restored buyer','date':'2026-04-01','data':{'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}}).json()
        c.post(b+'/records/'+row['id']+'/cancel',headers=h,json={'reason':'Synthetic duplicate'}).raise_for_status()
        for cycle in range(2):
            payload=c.get(b+'/data-export.json',headers=h).json()
            body=RecordTrailTest.restore_body(self,payload,'Journal history '+str(cycle))
            result=c.post('/api/backups/restore/commit',headers=h,json=body)
            self.assertEqual(result.status_code,200,result.text)
            b='/api/companies/'+result.json()['company_id']
            journals=c.get(b+'/journals',headers=h).json()
            self.assertEqual(len(journals),2)
            self.assertTrue(all(j['source_document'] and j['source_document']['cancelled'] for j in journals))
            for j in journals:
                self.assertEqual(j['source_document']['number'],row['number'])
                self.assertEqual(c.get(b+'/records/'+j['source_document']['id'],headers=h).status_code,200)
