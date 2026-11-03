import importlib.util, json, subprocess, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('vps_manage', Path(__file__).with_name('manage.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

RELEASE={'target':'apexbooks-vps','version':'1.5.0','source_sha':'a'*40,'api_image':'sha256:'+'b'*64,'web_image':'sha256:'+'c'*64}

class CutoverTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.stack = [patch.object(m,'release_config',return_value=RELEASE)]
        for name, value in {'BASE': root / 'app', 'STATE': root / 'app/shared', 'NGINX_ROOT': root / 'nginx',
                            'API': root / 'nginx/sites-enabled/apexbooks-api', 'WEB': root / 'nginx/sites-available/apexbooks-vps-web.conf',
                            'LINK': root / 'nginx/sites-enabled/apexbooks-vps-web.conf', 'PROXY': root / 'nginx/snippets/apexbooks-vps-proxy.conf'}.items():
            self.stack.append(patch.object(m, name, value))
        for item in self.stack: item.start()
        m.STATE.mkdir(parents=True)
        m.API.parent.mkdir(parents=True)
        m.WEB.parent.mkdir(parents=True)
        self.original = b'server {\n listen 443 ssl;\n server_name api.apexbooks.in;\n location / { proxy_pass http://127.0.0.1:8090; }\n}\n'
        m.API.write_bytes(self.original)
        self.other = m.API.parent / 'unrelated-app'
        self.other.write_bytes(b'untouched-other-app')
        self.commands = []
    def tearDown(self):
        for item in reversed(self.stack): item.stop()
        self.folder.cleanup()
    def execute(self, args, **kwargs):
        self.commands.append([str(x) for x in args])
        if args[:2] == ['nginx', '-T']:
            return SimpleNamespace(stdout='# configuration file ' + str(m.API) + ':\n' + m.API.read_text())
        return SimpleNamespace(stdout='')
    def test_existing_different_activation_refuses_before_private_settings_or_commands(self):
        (m.STATE/'activated.json').write_text(json.dumps({'release_identity':{**RELEASE,'source_sha':'d'*40}}))
        with patch.object(m,'settings',side_effect=AssertionError('Must not read private settings')),patch.object(m,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'another or unidentified release'):m.preflight()
        run.assert_not_called()

    def test_health_failure_leaves_proxy_unchanged(self):
        with patch.object(m, 'verify_local', side_effect=RuntimeError('unhealthy')), patch.object(m, 'run', side_effect=self.execute):
            with self.assertRaises(RuntimeError): m.activate()
        self.assertEqual(m.API.read_bytes(), self.original)
        self.assertFalse(m.WEB.exists())
        self.assertEqual(self.commands, [])
    def test_other_domain_in_api_file_refuses_replacement(self):
        m.API.write_text(self.original.decode().replace('api.apexbooks.in', 'other.example'))
        before = m.API.read_bytes()
        with patch.object(m, 'verify_local'), patch.object(m, 'run', side_effect=self.execute):
            with self.assertRaisesRegex(RuntimeError, 'unexpected domains'): m.activate()
        self.assertEqual(m.API.read_bytes(), before)
        self.assertFalse(m.WEB.exists())
    def test_failed_nginx_validation_restores_owned_files(self):
        failed = False
        def run(args, **kwargs):
            nonlocal failed
            if args == ['nginx', '-t'] and not failed:
                failed = True
                raise subprocess.CalledProcessError(1, args)
            return self.execute(args, **kwargs)
        with patch.object(m, 'verify_local'), patch.object(m, 'verify_public'), patch.object(m, 'run', side_effect=run):
            with self.assertRaises(subprocess.CalledProcessError): m.activate()
        self.assertEqual(m.API.read_bytes(), self.original)
        self.assertFalse(m.WEB.exists())
        self.assertFalse(m.LINK.is_symlink())
        self.assertFalse(m.PROXY.exists())
        self.assertEqual(self.other.read_bytes(), b'untouched-other-app')
    def test_success_changes_only_owned_sites_and_reloads_once(self):
        with patch.object(m, 'verify_local'), patch.object(m, 'verify_public'), patch.object(m, 'run', side_effect=self.execute): m.activate()
        self.assertIn(b'18091', m.API.read_bytes())
        self.assertIn(b'18090', m.WEB.read_bytes())
        self.assertTrue(m.LINK.is_symlink())
        self.assertEqual(self.commands.count(['systemctl', 'reload', 'nginx']), 1)
        self.assertFalse(any(command[0] == 'docker' for command in self.commands))
        self.assertEqual(self.other.read_bytes(), b'untouched-other-app')
    def test_atria_retirement_refuses_unexpected_service(self):
        (m.STATE / 'activated.json').write_text(json.dumps({'release_identity':RELEASE}))
        def run(args, **kwargs):
            self.commands.append(args)
            if args[:3] == ['docker', 'ps', '-aq']: return SimpleNamespace(stdout='unrelated-id')
            return SimpleNamespace(stdout='/unrelated-service')
        with patch.object(m, 'verify_public'), patch.object(m, 'run', side_effect=run):
            with self.assertRaisesRegex(RuntimeError, 'Unexpected Atria'): m.retire_atria()
        self.assertFalse(any(command[:2] in (['docker', 'stop'], ['docker', 'update']) for command in self.commands))
    def test_already_deleted_atria_is_not_recreated(self):
        (m.STATE / 'activated.json').write_text(json.dumps({'release_identity':RELEASE}))
        with patch.object(m, 'verify_public'), patch.object(m, 'run', return_value=SimpleNamespace(stdout='')) as run:
            m.retire_atria()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][:3], ['docker', 'ps', '-aq'])
        self.assertFalse((m.STATE / 'atria-restart-policies.json').exists())
    def test_failed_public_health_restores_original_proxy(self):
        with patch.object(m, 'verify_local'), patch.object(m, 'verify_public', side_effect=RuntimeError('wrong version')), patch.object(m, 'run', side_effect=self.execute):
            with self.assertRaisesRegex(RuntimeError, 'wrong version'): m.activate()
        self.assertEqual(m.API.read_bytes(), self.original)
        self.assertFalse(m.WEB.exists())
        self.assertFalse(m.LINK.is_symlink())
        self.assertEqual(self.other.read_bytes(), b'untouched-other-app')
        self.assertFalse((m.STATE / 'activated.json').exists())
    def test_retirement_stops_only_confirmed_atria_containers_and_retains_data(self):
        (m.STATE / 'activated.json').write_text(json.dumps({'release_identity':RELEASE}))
        def run(args, **kwargs):
            self.commands.append(args)
            if args[:3] == ['docker', 'ps', '-aq']: return SimpleNamespace(stdout='api-id db-id')
            if args[:2] == ['docker', 'inspect']:
                if args[3] == '{{.Name}}': return SimpleNamespace(stdout='/atria-server-api-1' if args[-1] == 'api-id' else '/atria-server-db-1')
                return SimpleNamespace(stdout=json.dumps({'Name': 'unless-stopped', 'MaximumRetryCount': 0}))
            return SimpleNamespace(stdout='')
        with patch.object(m, 'verify_public'), patch.object(m, 'run', side_effect=run): m.retire_atria()
        self.assertIn(['docker', 'stop', '--time', '45', 'api-id', 'db-id'], self.commands)
        self.assertIn(['docker', 'update', '--restart=no', 'api-id', 'db-id'], self.commands)
        self.assertEqual(set(json.loads((m.STATE / 'atria-restart-policies.json').read_text())), {'api-id', 'db-id'})
        self.assertFalse(any(command[:2] in (['docker', 'rm'], ['docker', 'volume'], ['docker', 'system']) for command in self.commands))

class HttpsProbeTests(unittest.TestCase):
    def setUp(self):
        self.release=patch.object(m,'release_config',return_value=RELEASE);self.release.start();self.addCleanup(self.release.stop)
        self.identity=patch.object(m,'verify_image_identity');self.identity.start();self.addCleanup(self.identity.stop)
    def test_reload_probe_retries_then_passes(self):
        with patch.object(m, 'public_probe_once', side_effect=[RuntimeError('old worker returned HTTP 404'), None]) as probe, patch.object(m.time, 'sleep'):
            m.verify_public()
        self.assertEqual(probe.call_count, 2)
    def test_persistent_failure_preserves_diagnostic_and_stops(self):
        with patch.object(m, 'public_probe_once', side_effect=RuntimeError('curl exit 60: certificate mismatch')), patch.object(m.time, 'monotonic', side_effect=[0, 46]), patch.object(m.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'curl exit 60: certificate mismatch'): m.verify_public()
        sleep.assert_not_called()
    def test_tls_and_origin_checks_stay_enabled(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            return SimpleNamespace(stdout=json.dumps({'status':'ready','version':'1.5.0','build_revision':RELEASE['source_sha']}))
        with patch.object(m, 'run', side_effect=run): m.ready('https://api.apexbooks.in/api/ready', 'api.apexbooks.in')
        self.assertIn('--noproxy', calls[0])
        self.assertIn('--resolve', calls[0])
        self.assertNotIn('-k', calls[0])
        self.assertNotIn('--insecure', calls[0])
    def test_curl_errors_include_exit_code_and_stderr(self):
        error = subprocess.CalledProcessError(22, ['curl'], stderr='curl: (22) The requested URL returned error: 502')
        with patch.object(m, 'run', side_effect=error):
            with self.assertRaisesRegex(RuntimeError, 'curl exit 22:.*502'): m.ready('https://api.apexbooks.in/api/ready', 'api.apexbooks.in')

class ReleaseIdentityTests(unittest.TestCase):
    def test_missing_invalid_unknown_release_fails_closed_without_commands(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(m,'ROOT',Path(directory)), patch.object(m,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'release.json'):m.release_config()
            for change in ({'target':'unknown'},{'version':'1.5;echo nope'},{'source_sha':'abcd'},{'api_image':'apex:latest'}):
                (Path(directory)/'release.json').write_text(json.dumps({**RELEASE,**change}))
                with self.assertRaises(RuntimeError):m.release_config()
            (Path(directory)/'release.json').write_text(json.dumps(RELEASE))
            self.assertEqual(m.release_config(),RELEASE);run.assert_not_called()

    def test_image_revision_version_and_running_identity_must_all_match(self):
        def execute(args,**kwargs):
            if args[:3]==['docker','image','inspect']:
                return SimpleNamespace(stdout=json.dumps({'Id':args[-1],'Config':{'Labels':{'org.opencontainers.image.revision':RELEASE['source_sha'],'org.opencontainers.image.version':RELEASE['version']}}}))
            return SimpleNamespace(stdout=RELEASE['api_image'])
        with patch.object(m,'release_config',return_value=RELEASE),patch.object(m,'run',side_effect=execute),patch.object(m,'compose',return_value=SimpleNamespace(stdout='synthetic-container')):
            m.verify_image_identity()
            with self.assertRaisesRegex(RuntimeError,'Deployed image identity mismatch'):m.verify_image_identity(running=True)
        for label in ('org.opencontainers.image.revision','org.opencontainers.image.version'):
            labels={'org.opencontainers.image.revision':RELEASE['source_sha'],'org.opencontainers.image.version':RELEASE['version']};labels[label]='unknown'
            with patch.object(m,'release_config',return_value=RELEASE),patch.object(m,'run',return_value=SimpleNamespace(stdout=json.dumps({'Id':RELEASE['api_image'],'Config':{'Labels':labels}}))):
                with self.assertRaisesRegex(RuntimeError,'release identity mismatch'):m.verify_image_identity()

    def test_compose_uses_only_configured_immutable_image_references(self):
        with patch.object(m,'release_config',return_value=RELEASE),patch.object(m,'run',return_value=SimpleNamespace(stdout='')) as run:
            m.compose('ps','-q','api')
        env=run.call_args.kwargs['env']
        self.assertEqual(env['APEX_API_IMAGE'],RELEASE['api_image']);self.assertEqual(env['APEX_WEB_IMAGE'],RELEASE['web_image'])
        compose=Path(__file__).with_name('compose.yml').read_text()
        self.assertIn('${APEX_API_IMAGE:?',compose);self.assertIn('${APEX_WEB_IMAGE:?',compose)
        self.assertNotIn('1.3.0',compose)
        self.assertEqual(env['APEX_SOURCE_SHA'],RELEASE['source_sha'])
        self.assertIn('APEX_BUILD_SHA: ${APEX_SOURCE_SHA:?',compose)

    def test_docker_build_identity_is_explicit_and_unknown_when_absent(self):
        root=Path(__file__).resolve().parents[2]
        backend=(root/'backend/Dockerfile').read_text()
        frontend=(root/'frontend/Dockerfile').read_text()
        self.assertIn('ARG APEX_BUILD_SHA=unknown',backend)
        self.assertIn('ENV APEX_BUILD_SHA=${APEX_BUILD_SHA}',backend)
        self.assertIn('org.opencontainers.image.revision=${APEX_BUILD_SHA}',backend)
        self.assertLess(frontend.index('ARG VITE_BUILD_SHA=unknown'),frontend.index('RUN npm run build'))
        self.assertLess(frontend.index('ENV VITE_BUILD_SHA=${VITE_BUILD_SHA}'),frontend.index('RUN npm run build'))
        final=frontend.split('FROM nginx:alpine',1)[1]
        self.assertIn('ARG VITE_BUILD_SHA=unknown',final)
        self.assertIn('org.opencontainers.image.revision=${VITE_BUILD_SHA}',final)
        for source in (frontend,backend):
            self.assertIn('ARG APEX_RELEASE_VERSION=unknown',source)
            self.assertIn('org.opencontainers.image.version=${APEX_RELEASE_VERSION}',source)
            self.assertNotIn('git rev-parse',source)
        compose=(root/'docker-compose.yml').read_text()
        self.assertEqual(compose.count('APEX_BUILD_SHA: ${APEX_SOURCE_SHA:-unknown}'),2)
        self.assertIn('VITE_BUILD_SHA: ${APEX_SOURCE_SHA:-unknown}',compose)

    def test_shell_release_validation_failure_stops_before_eval_or_bootstrap(self):
        folder=Path(__file__).parent
        install=(folder/'install.sh').read_text()
        snippet=install[install.index('release_exports='):install.index('python3 deploy/vps/manage.py preflight')]
        bootstrap=(folder/'bootstrap.sh').read_text()
        bootstrap=bootstrap[bootstrap.index('identity_text='):bootstrap.index('release="${identity[0]}')]
        # Only a failing mock function executes; no deployment commands are present.
        for body in (snippet,bootstrap):
            result=subprocess.run(['bash','-c','set -euo pipefail; python3() { return 17; };\n'+body+'\necho UNEXPECTED_CONTINUE'],capture_output=True,text=True)
            self.assertEqual(result.returncode,17,result.stderr);self.assertNotIn('UNEXPECTED_CONTINUE',result.stdout)

    def test_readiness_requires_exact_served_source_revision(self):
        for revision in (None,'unknown','d'*40,RELEASE['source_sha']):
            with patch.object(m,'release_config',return_value=RELEASE),patch.object(m,'run',return_value=SimpleNamespace(stdout=json.dumps({'status':'ready','version':RELEASE['version'],'build_revision':revision}))):
                if revision==RELEASE['source_sha']:m.ready('https://synthetic.invalid/api/ready')
                else:
                    with self.assertRaisesRegex(RuntimeError,'source revision'):m.ready('https://synthetic.invalid/api/ready')

    def test_wrong_ready_version_and_old_activation_marker_are_rejected(self):
        with patch.object(m,'release_config',return_value=RELEASE),patch.object(m,'run',return_value=SimpleNamespace(stdout='{"status":"ready","version":"1.3.0"}')):
            with self.assertRaisesRegex(RuntimeError,'Unexpected application/version'):m.ready('https://synthetic.invalid/api/ready')
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'STATE',Path(directory)),patch.object(m,'release_config',return_value=RELEASE):
            for state in ({'release':'1.3.0'},{'release_identity':{**RELEASE,'source_sha':'d'*40}}):
                (Path(directory)/'activated.json').write_text(json.dumps(state))
                with self.assertRaisesRegex(RuntimeError,'another or unidentified release'):m.activation_state()

class PackagingRecipeTests(unittest.TestCase):
    def test_pasted_recipe_stops_before_build_on_mismatch_or_dirty_tree(self):
        text=Path(__file__).with_name('README.md').read_text()
        recipe=text.split('### Explicit image build identity propagation',1)[1].split('```bash\n',1)[1].split('```',1)[0]
        for mismatch in (True,False):
            sha='b'*40 if mismatch else 'a'*40
            prefix=("export APEX_SOURCE_SHA="+'a'*40+" APEX_RELEASE_VERSION=1.5.0\n"
                    "git() { if [[ $1 == rev-parse ]]; then printf '%s' "+sha+"; else printf 'dirty'; fi; }\n"
                    "docker() { printf 'UNEXPECTED_BUILD'; return 99; }\n")
            result=subprocess.run(['bash','-c',prefix+recipe],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('UNEXPECTED_BUILD',result.stdout+result.stderr)

if __name__ == '__main__': unittest.main()
