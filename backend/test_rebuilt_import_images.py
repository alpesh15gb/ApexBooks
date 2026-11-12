import base64
import io
import unittest
from PIL import Image
import test_completion


class RebuiltImportImagesTest(unittest.TestCase):
    def image(self, fmt='PNG', size=(12,12), truncate=0, mime=None):
        output=io.BytesIO();Image.new('RGB',size,(17,90,130)).save(output,format=fmt)
        raw=output.getvalue();raw=raw[:-truncate] if truncate else raw
        return 'data:image/'+(mime or {'PNG':'png','JPEG':'jpeg','GIF':'png'}[fmt])+';base64,'+base64.b64encode(raw).decode()

    def test_malformed_images_reject_creation_and_atomic_import(self):
        c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
        cases=[self.image('JPEG',truncate=20),self.image('JPEG',mime='png'),self.image('GIF'),self.image(size=(1001,1000)),'data:image/png;base64,bm90LWFuLWltYWdl']
        for index,value in enumerate(cases):
            for field in ('image_data_url','image_thumbnail'):
                with self.subTest(index=index,field=field):
                    rows=[{'name':'Valid neighbour '+str(index)},{'name':'Invalid image '+str(index),field:value}]
                    before=c.get(b+'/records',headers=h).json()
                    preview=c.post(b+'/masters/import',headers=h,json={'kind':'item','rows':rows});self.assertEqual(preview.status_code,200,preview.text)
                    self.assertEqual(preview.json()['ready'],1);self.assertEqual(preview.json()['errors'][0]['row'],3)
                    commit=c.post(b+'/masters/import',headers=h,json={'kind':'item','rows':rows,'dry_run':False});self.assertEqual(commit.status_code,422,commit.text)
                    create=c.post(b+'/records',headers=h,json={'kind':'item','name':'Invalid direct','data':{field:value}});self.assertEqual(create.status_code,422,create.text)
                    self.assertEqual(before,c.get(b+'/records',headers=h).json())

    def test_supported_images_and_text_identity_survive_import(self):
        c,h,b=test_completion.CompletionTest.client_context(self,'unregistered')
        rows=[{'name':'=Synthetic formula text','barcode':'0012345','hsn':'0101','image_data_url':self.image(),'image_thumbnail':self.image('JPEG')}, {'name':'#N/A','image_data_url':self.image('JPEG')}]
        for dry in (True,False):
            response=c.post(b+'/masters/import',headers=h,json={'kind':'item','rows':rows,'dry_run':dry});self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['ready'],2)
        saved=c.get(b+'/records',headers=h).json();item=next(r for r in saved if r['name']==rows[0]['name'])
        self.assertEqual(item['data']['barcode'],'0012345');self.assertEqual(item['data']['hsn'],'0101');self.assertEqual(item['data']['image_data_url'],rows[0]['image_data_url'])
        again=c.post(b+'/masters/import',headers=h,json={'kind':'item','rows':rows,'dry_run':False});self.assertEqual(again.json()['created'],0);self.assertEqual(again.json()['duplicates'],2)
        other=c.post('/api/companies',headers=h,json={'name':'Separate synthetic books','tax_mode':'unregistered'}).json()['id']
        response=c.post('/api/companies/'+other+'/masters/import',headers=h,json={'kind':'item','rows':rows,'dry_run':False});self.assertEqual(response.json()['created'],2)
