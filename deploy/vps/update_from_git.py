"""Stage/build a clean Git revision, then update only the existing Apex project."""
import argparse
import datetime
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

BASE=Path('/opt/apexbooks-vps')
SOURCE=Path(__file__).resolve().parents[2]
VERSION='1.5.0'


def run(args,**kwargs):
    return subprocess.run([str(a) for a in args],check=True,**kwargs)


def output(args):return run(args,cwd=SOURCE,capture_output=True,text=True).stdout.strip()


def controller(root):
    spec=importlib.util.spec_from_file_location('apex_release_controller',root/'deploy/vps/manage.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def manifest(root):
    files=sorted(p for p in root.rglob('*') if p.is_file() and p.name!='VPS_FILES.sha256' and '__pycache__' not in p.parts)
    (root/'VPS_FILES.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(root).as_posix()+'\n' for p in files),encoding='utf-8')


def stage(root,sha):
    if root.exists():
        run(['sha256sum','--check','VPS_FILES.sha256'],cwd=root)
        controller(root).verify_image_identity()
        print('Exact release is already staged: '+str(root));return
    if shutil.disk_usage(BASE).free<5*1024**3:raise RuntimeError('At least 5 GB free disk is required for staging/building')
    BASE.joinpath('releases').mkdir(exist_ok=True)
    temporary=BASE/'releases'/('.building-'+sha+'-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    temporary.mkdir()
    archive=run(['git','archive',sha,'backend','frontend','deploy','docs'],cwd=SOURCE,capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:bundle.extractall(temporary,filter='data')
    identity={'target':'apexbooks-vps','version':VERSION,'source_sha':sha}
    # Sequential builds reduce peak memory/CPU pressure on the shared VPS.
    for service,arg in [('api','APEX_BUILD_SHA'),('web','VITE_BUILD_SHA')]:
        tag='apexbooks-vps-'+service+':'+VERSION+'-'+sha
        print('Building '+service+' from '+sha,flush=True)
        run(['docker','build','--platform','linux/amd64','--build-arg',arg+'='+sha,
             '--build-arg','APEX_RELEASE_VERSION='+VERSION,'-t',tag,str(temporary/('backend' if service=='api' else 'frontend'))])
        data=json.loads(output(['docker','image','inspect',tag]))[0]
        labels=data['Config']['Labels']
        if data['Architecture']!='amd64' or labels.get('org.opencontainers.image.revision')!=sha or labels.get('org.opencontainers.image.version')!=VERSION:
            raise RuntimeError('Built image identity mismatch: '+service)
        identity[service+'_image']=data['Id']
    (temporary/'release.json').write_text(json.dumps(identity,indent=2)+'\n',encoding='utf-8')
    manifest(temporary)
    temporary.rename(root)
    m=controller(root);m.verify_image_identity()
    print('Staged '+str(root)+'. Running services have not been restarted.')


def apply(root,waived,paused):
    if not waived or not paused:
        raise RuntimeError('Use --without-backup --writers-paused only after pausing every Apex writer. Verified-backup upgrades remain available through the controller README.')
    m=controller(root);release=m.release_config()
    marker=(m.STATE/'activated.json').read_bytes();previous=json.loads(marker)
    if previous.get('release_identity')==release:
        m.verify_local();m.verify_public();print('This release is already active.');return
    images={}
    for service in ('api','web'):
        cid=m.compose('ps','-q',service).stdout.strip()
        if not cid or len(cid.splitlines())!=1:raise RuntimeError('Expected one running Apex '+service+' service')
        images[service]=m.run(['docker','inspect','--format','{{.Image}}',cid],capture_output=True).stdout.strip()
    if any(images[key]==release[key+'_image'] for key in images):
        raise RuntimeError('Candidate containers already changed. Retain the prepared plan and use the resume action.')
    plan={'target_release_identity':release,'previous_activation_sha256':hashlib.sha256(marker).hexdigest(),
          'previous_images':images,'database_backup_reference':None,'isolated_restore_verified':False,
          'production_clone_rehearsed':False,'writers_paused':True,'backup_policy':'operator_waived',
          'backup_waiver_reason':'Operator explicitly requested no backup at this stage'}
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for name in ('upgrade-plan.json','upgrade-other-apps.json'):
        path=m.STATE/name
        if path.exists():m.atomic(m.BASE/'backups'/('prior-'+stamp+'-'+name),path.read_bytes(),0o600)
    m.atomic(m.STATE/'upgrade-plan.json',json.dumps(plan,indent=2).encode(),0o600)
    m.atomic(m.STATE/'upgrade-other-apps.json',json.dumps(m.other_containers(),indent=2).encode(),0o600)
    print('Proceeding with the recorded operator backup waiver; no backup or restore rehearsal is claimed.',flush=True)
    m.prepare_upgrade()
    m.compose('stop','api','web')
    print('Applying versioned migrations to the existing database.',flush=True)
    m.compose('run','--rm','--no-deps','api','python','migrate.py')
    m.compose('up','-d','--no-build','--pull','never','api','web')
    finish(m)


def finish(m):
    m.finish_upgrade()
    before=json.loads((m.STATE/'upgrade-other-apps.json').read_text())
    if m.other_containers()!=before:raise RuntimeError('An unrelated application changed during this window; review the saved baseline.')
    print('Apex API/web and both HTTPS domains verified. Other running applications match their pre-upgrade baseline.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['stage','apply','verify','resume'])
    parser.add_argument('--source-sha',required=True)
    parser.add_argument('--without-backup',action='store_true')
    parser.add_argument('--writers-paused',action='store_true')
    args=parser.parse_args()
    if os.geteuid()!=0:raise RuntimeError('Run on the existing Apex Books VPS as root')
    if not re.fullmatch(r'[0-9a-f]{40}',args.source_sha):raise RuntimeError('Full tested source SHA required')
    if output(['git','remote','get-url','origin']) not in ('https://github.com/alpesh15gb/ApexBooks.git','git@github.com:alpesh15gb/ApexBooks.git'):
        raise RuntimeError('Unexpected Git origin')
    if output(['git','rev-parse','HEAD'])!=args.source_sha or output(['git','status','--porcelain','--untracked-files=no']):
        raise RuntimeError('Checkout must be clean and match the explicit tested source SHA')
    root=BASE/'releases'/(VERSION+'-'+args.source_sha)
    if args.action=='stage':stage(root,args.source_sha);return
    if not (root/'release.json').is_file():raise RuntimeError('Stage this release before applying/verifying')
    run(['sha256sum','--check','VPS_FILES.sha256'],cwd=root,capture_output=True)
    if args.action=='apply':apply(root,args.without_backup,args.writers_paused)
    elif args.action=='resume':
        if not args.writers_paused:raise RuntimeError('Keep Apex writers paused before resuming')
        m=controller(root);m.upgrade_plan();m.compose('up','-d','--no-build','--pull','never','api','web');finish(m)
    else:
        m=controller(root);m.verify_local();m.verify_public()


if __name__=='__main__':
    try:main()
    except Exception as error:
        if isinstance(error,subprocess.CalledProcessError):print('Deployment command failed: '+str(error.cmd[0])+'. Private command output withheld; existing services were not globally restarted.')
        else:print(str(error))
        raise SystemExit(1)
