import hashlib,importlib.util,io,json,tarfile,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
spec=importlib.util.spec_from_file_location('git_updater',Path(__file__).with_name('update_from_git.py'))
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)

class GitUpdaterTest(unittest.TestCase):
    def test_apply_requires_explicit_choices_before_controller_access(self):
        for waived,paused in ((False,True),(True,False),(False,False)):
            with patch.object(u,'controller') as loader,self.assertRaises(RuntimeError):u.apply(Path('/unused'),waived,paused)
            loader.assert_not_called()

    def test_staging_uses_git_archive_and_sequential_source_identified_builds(self):
        sha='a'*40
        memory=io.BytesIO()
        with tarfile.open(fileobj=memory,mode='w') as archive:
            for name in ('backend/Dockerfile','frontend/Dockerfile','deploy/vps/manage.py'):
                data=b'public source\n';entry=tarfile.TarInfo(name);entry.size=len(data);archive.addfile(entry,io.BytesIO(data))
        calls=[]
        def run(args,**kwargs):
            calls.append(args)
            return SimpleNamespace(stdout=memory.getvalue() if args[:2]==['git','archive'] else '')
        def inspect(args):
            tag=args[-1];key='APEX_BUILD_SHA' if '-api:' in tag else 'VITE_BUILD_SHA'
            return json.dumps([{'Id':'sha256:'+('b' if key=='APEX_BUILD_SHA' else 'c')*64,'Architecture':'amd64',
              'Config':{'Labels':{'org.opencontainers.image.revision':sha,'org.opencontainers.image.version':u.VERSION}}}])
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);root=base/'releases'/('1.5.0-'+sha);m=Mock()
            with patch.object(u,'BASE',base),patch.object(u,'run',side_effect=run),patch.object(u,'output',side_effect=inspect),patch.object(u,'controller',return_value=m),patch.object(u.shutil,'disk_usage',return_value=SimpleNamespace(free=8*1024**3)):
                u.stage(root,sha)
            builds=[args for args in calls if args[:2]==['docker','build']]
            self.assertEqual(len(builds),2);self.assertIn('APEX_BUILD_SHA='+sha,builds[0]);self.assertIn('VITE_BUILD_SHA='+sha,builds[1])
            self.assertFalse((root/'.env').exists());self.assertTrue((root/'VPS_FILES.sha256').is_file())
            self.assertEqual(json.loads((root/'release.json').read_text())['source_sha'],sha)
            m.verify_image_identity.assert_called_once()

    def test_apply_records_truthful_waiver_and_only_updates_api_web(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'shared';state.mkdir();(state/'activated.json').write_text(json.dumps({'backup':'existing-nginx-snapshot'}))
            release={'api_image':'sha256:'+'a'*64,'web_image':'sha256:'+'b'*64}
            calls=[]
            def compose(*args):
                calls.append(args);return SimpleNamespace(stdout=args[-1] if args[:2]==('ps','-q') else '')
            def atomic(path,data,mode):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            m=SimpleNamespace(STATE=state,BASE=Path(directory),release_config=lambda:release,compose=compose,
                 run=lambda *a,**k:SimpleNamespace(stdout='sha256:'+'c'*64),atomic=atomic,other_containers=lambda:{},prepare_upgrade=Mock())
            with patch.object(u,'controller',return_value=m),patch.object(u,'finish') as finish:u.apply(Path('/unused'),True,True)
            plan=json.loads((state/'upgrade-plan.json').read_text())
            self.assertIsNone(plan['database_backup_reference']);self.assertFalse(plan['isolated_restore_verified'])
            self.assertEqual(plan['backup_policy'],'operator_waived');m.prepare_upgrade.assert_called_once();finish.assert_called_once_with(m)
            self.assertEqual(calls[2:], [('stop','api','web'),('run','--rm','--no-deps','api','python','migrate.py'),('up','-d','--no-build','--pull','never','api','web')])

if __name__=='__main__':unittest.main()
