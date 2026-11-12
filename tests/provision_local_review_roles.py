"""Provision two disposable local QA roles, never production or SMTP.
Run in the reviewer's desktop environment, where its loopback API is reachable.
"""
import argparse,getpass,json,secrets,urllib.request,urllib.error,urllib.parse,os
from pathlib import Path

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise RuntimeError('Redirect refused: local QA only')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',required=True);p.add_argument('--owner-email',required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();url=urllib.parse.urlsplit(args.base_url)
    if url.scheme!='http' or url.hostname not in {'127.0.0.1','localhost','::1'} or url.path not in {'','/'} or url.username or url.password or url.query or url.fragment:
        p.error('Use only an HTTP loopback origin without credentials/path/query')
    if args.output.exists():p.error('Output already exists; preserve the earlier credentials')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    def call(path,body=None,token='',expected=200):
        req=urllib.request.Request(args.base_url.rstrip('/')+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
        try:
            with opener.open(req,timeout=15) as response:status=response.status;value=json.load(response)
        except urllib.error.HTTPError as e:status=e.code;value=json.load(e)
        if status!=expected:raise RuntimeError(f'{path}: expected HTTP {expected}, received {status}; no credentials logged')
        return value
    owner=call('/api/auth/login',{'email':args.owner_email,'password':getpass.getpass('Disposable local owner password: ')})['token']
    companies=call('/api/companies',token=owner)
    matches=[c for c in companies if c['name']=='QA Evidence Restore' and c.get('role')=='owner']
    if len(matches)!=1:raise RuntimeError('Expected exactly one owned company named QA Evidence Restore; no users created')
    company=matches[0];base='/api/companies/'+company['id'];members=call(base+'/members',token=owner)
    results=[]
    # Create the protected output first so partial provisioning remains recoverable.
    fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as out:
        def save():
            out.seek(0);json.dump({'base_url':args.base_url,'company_id':company['id'],'company_name':company['name'],'accounts':results},out,indent=2);out.truncate();out.flush();os.fsync(out.fileno())
        for role in ('viewer','editor'):
            account={'email':f'qa-{role}-{secrets.token_hex(6)}@apex-review.invalid','password':secrets.token_urlsafe(24),'role':role,'status':'planned'};results.append(account);save()
            call('/api/auth/register',{'email':account['email'],'password':account['password']});account['status']='registered';save()
            token=call('/api/auth/login',{'email':account['email'],'password':account['password']})['token']
            call(base+'/members',{'email':account['email'],'role':role},owner,201);account['status']='member';save()
            visible=call('/api/companies',token=token)
            assert next(c for c in visible if c['id']==company['id'])['role']==role
            call(base+'/records',token=token)
            call(base+'/masters/import',{'kind':'party','dry_run':True,'rows':[{'name':'Synthetic role preview only'}]},token,403 if role=='viewer' else 200)
            account['status']='login/read/role/dry-run verified';save()
        after=call(base+'/members',token=owner)
        assert all(member in after for member in members),'Existing membership changed unexpectedly'
    print('Two local roles verified; protected synthetic credentials saved to',args.output)

if __name__=='__main__':main()
