"""Owner labels distinguish books without changing legal identity or print names."""
import base64,io,json,unittest
from uuid import uuid4
from pypdf import PdfReader
import test_completion

class BookLabelTest(unittest.TestCase):
    context=test_completion.CompletionTest.client_context
    def test_optional_owner_label_preserves_legal_identity_and_old_clients(self):
        c,h,b=self.context()
        def create(label=None):
            data={'name':'Identical legal name','tax_mode':'unregistered'}
            if label is not None:data['book_label']=label
            r=c.post('/api/companies',headers=h,json=data);self.assertEqual(r.status_code,200,r.text);return r.json()
        first=create('  Owner book A  ');second=create('Owner book B');old=create()
        self.assertEqual(first['book_label'],'Owner book A');self.assertEqual(second['book_label'],'Owner book B');self.assertEqual(old['book_label'],'')
        self.assertNotEqual(first['id'],second['id']);self.assertEqual(first['name'],second['name'])
        path='/api/companies/'+first['id'];body={'name':first['name'],'address':'Updated billing office'}
        legacy=c.patch(path,headers=h,json=body);self.assertEqual(legacy.status_code,200,legacy.text);self.assertEqual(legacy.json()['book_label'],'Owner book A')
        for value in (None,42,'x'*81):self.assertEqual(c.patch(path,headers=h,json={**body,'book_label':value}).status_code,422)
        cleared=c.patch(path,headers=h,json={**body,'book_label':'  '});self.assertEqual(cleared.status_code,200,cleared.text);self.assertEqual(cleared.json()['book_label'],'')
        companies=c.get('/api/companies',headers=h).json();self.assertEqual(next(x for x in companies if x['id']==second['id'])['book_label'],'Owner book B')

    def test_label_is_owner_only_and_never_printed_as_legal_name(self):
        c,h,b=self.context();company=next(x for x in c.get('/api/companies',headers=h).json() if b.endswith(x['id']))
        body={'name':company['name'],'book_label':'PRIVATE-BOOK-ALIAS-ONLY'}
        changed=c.patch(b,headers=h,json=body);self.assertEqual(changed.status_code,200,changed.text)
        creds={'email':uuid4().hex+'@booklabel.invalid','password':'Synthetic-booklabel-password'};c.post('/api/auth/register',json=creds).raise_for_status()
        editor={'Authorization':'Bearer '+c.post('/api/auth/login',json=creds).json()['token']}
        self.assertEqual(c.patch(b,headers=editor,json=body).status_code,404)
        c.post(b+'/members',headers=h,json={'email':creds['email'],'role':'editor'}).raise_for_status()
        self.assertEqual(c.patch(b,headers=editor,json=body).status_code,403)
        invoice=c.post(b+'/records',headers=h,json={'kind':'sales_invoice','name':'Label buyer','date':'2026-04-02','data':{'lines':[{'description':'Service','quantity':1,'rate':100,'gst_rate':0}]}});self.assertEqual(invoice.status_code,200,invoice.text)
        pdf=c.get(b+'/documents/'+invoice.json()['id']+'.pdf',headers=h);self.assertEqual(pdf.status_code,200)
        text=' '.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
        self.assertIn(company['name'],text);self.assertNotIn(body['book_label'],text)

    def test_portable_restore_keeps_alias_and_accepts_old_backup_missing_it(self):
        c,h,b=self.context();company=next(x for x in c.get('/api/companies',headers=h).json() if b.endswith(x['id']))
        c.patch(b,headers=h,json={'name':company['name'],'book_label':'Book for separate records'}).raise_for_status()
        payload=c.get(b+'/data-export.json',headers=h).json();self.assertEqual(payload['company']['book_label'],'Book for separate records')
        def encoded(name):return {'company_name':name,'backup_base64':base64.b64encode(json.dumps(payload).encode()).decode()}
        for present in (True,False):
            if not present:payload['company'].pop('book_label')
            data=encoded('Restored legal '+str(present));preview=c.post('/api/backups/restore/preview',headers=h,json=data);self.assertEqual(preview.status_code,200,preview.text)
            result=c.post('/api/backups/restore/commit',headers=h,json={**data,'digest':preview.json()['digest']});self.assertEqual(result.status_code,200,result.text)
            restored=next(x for x in c.get('/api/companies',headers=h).json() if x['id']==result.json()['company_id'])
            self.assertEqual(restored['name'],data['company_name']);self.assertEqual(restored['book_label'],'Book for separate records' if present else '')
        for bad in (None,False,'x'*81):
            payload['company']['book_label']=bad;self.assertEqual(c.post('/api/backups/restore/preview',headers=h,json=encoded('Invalid')).status_code,422)

    def test_public_capabilities_are_financial_data_free_and_truthful(self):
        c,h,b=self.context();r=c.get('/api/capabilities');self.assertEqual(r.status_code,200,r.text);value=r.json()
        self.assertEqual(value['capabilities_version'],1);self.assertIn('company_book_labels',value['supported_features']);self.assertIn('recurring_drafts',value['supported_features'])
        import main
        self.assertEqual(value['api_version'],main.app.version);self.assertEqual(value['build_revision'],main.BUILD_REVISION)
        self.assertRegex(value['build_revision'],r'^(unknown|[0-9a-f]{40}|[0-9a-f]{64})$')
        self.assertEqual('document_attachments' in value['supported_features'],bool(getattr(main.app.state,'document_attachments_ready',False) and getattr(main.app.state,'chunked_backups_ready',False)))
        self.assertEqual('chunked_backups' in value['supported_features'],bool(getattr(main.app.state,'chunked_backups_ready',False)))
        self.assertEqual(value['business_timezone'],'Asia/Kolkata');self.assertNotIn('companies',value);self.assertNotIn('records',value)

if __name__=='__main__':unittest.main()
