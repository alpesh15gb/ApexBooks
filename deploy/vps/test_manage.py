import importlib.util, json, subprocess, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('vps_manage', Path(__file__).with_name('manage.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class CutoverTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.stack = []
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
        (m.STATE / 'activated.json').write_text('{}')
        def run(args, **kwargs):
            self.commands.append(args)
            if args[:3] == ['docker', 'ps', '-aq']: return SimpleNamespace(stdout='unrelated-id')
            return SimpleNamespace(stdout='/unrelated-service')
        with patch.object(m, 'verify_public'), patch.object(m, 'run', side_effect=run):
            with self.assertRaisesRegex(RuntimeError, 'Unexpected Atria'): m.retire_atria()
        self.assertFalse(any(command[:2] in (['docker', 'stop'], ['docker', 'update']) for command in self.commands))
    def test_already_deleted_atria_is_not_recreated(self):
        (m.STATE / 'activated.json').write_text('{}')
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
        (m.STATE / 'activated.json').write_text('{}')
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
            return SimpleNamespace(stdout='{"status":"ready","version":"1.3.0"}')
        with patch.object(m, 'run', side_effect=run): m.ready('https://api.apexbooks.in/api/ready', 'api.apexbooks.in')
        self.assertIn('--noproxy', calls[0])
        self.assertIn('--resolve', calls[0])
        self.assertNotIn('-k', calls[0])
        self.assertNotIn('--insecure', calls[0])
    def test_curl_errors_include_exit_code_and_stderr(self):
        error = subprocess.CalledProcessError(22, ['curl'], stderr='curl: (22) The requested URL returned error: 502')
        with patch.object(m, 'run', side_effect=error):
            with self.assertRaisesRegex(RuntimeError, 'curl exit 22:.*502'): m.ready('https://api.apexbooks.in/api/ready', 'api.apexbooks.in')

if __name__ == '__main__': unittest.main()
