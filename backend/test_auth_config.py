import unittest
import subprocess
import sys
import os
from pathlib import Path
from auth_config import require_jwt_secret


def isolated_startup_environment(directory, runtime_environment):
    # Keep real application credentials/configuration out of the child. Windows
    # needs SystemRoot to initialize networking DLLs before the API is imported.
    environment = {'DATABASE_URL': 'sqlite://', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(directory)}
    system_root = runtime_environment.get('SystemRoot') or runtime_environment.get('SYSTEMROOT')
    if system_root:
        environment['SystemRoot'] = system_root
    return environment


class SigningConfigurationTest(unittest.TestCase):
    def test_startup_environment_preserves_runtime_root_but_excludes_app_secrets(self):
        directory = Path(__file__).parent
        for root_key in ('SystemRoot', 'SYSTEMROOT'):
            supplied = {root_key: r'C:\Windows', 'DATABASE_URL': 'postgresql://private.invalid/books',
                        'JWT_SECRET': 'private-parent-secret', 'OPENAI_API_KEY': 'private-parent-key',
                        'PYTHONPATH': 'untrusted-parent-modules', 'PATH': 'untrusted-parent-path'}
            actual = isolated_startup_environment(directory, supplied)
            self.assertEqual(actual, {'SystemRoot': r'C:\Windows', 'DATABASE_URL': 'sqlite://',
                                      'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(directory)})
        self.assertNotIn('SystemRoot', isolated_startup_environment(directory, {}))

    def test_missing_short_and_documented_placeholders_fail_for_every_database(self):
        for database in ('sqlite://', 'sqlite:///./example.db', 'postgresql+psycopg://synthetic.invalid/test'):
            for secret in (None, '', ' ', 'x' * 31, 'development-only-change-me', 'replace-with-a-long-random-secret'):
                with self.subTest(database=database, secret_length=len(secret or '')):
                    env = {'DATABASE_URL': database}
                    if secret is not None:
                        env['JWT_SECRET'] = secret
                    with self.assertRaisesRegex(RuntimeError, 'Set JWT_SECRET'):
                        require_jwt_secret(env)

    def test_explicit_long_secret_is_retained_without_silent_rewriting(self):
        value = 'synthetic-test-signing-key-never-production'
        self.assertEqual(require_jwt_secret({'JWT_SECRET': value}), value)
        self.assertEqual(require_jwt_secret({'JWT_SECRET': ' ' + value + ' '}), ' ' + value + ' ')

    def test_configuration_error_never_echoes_secret(self):
        value = 'synthetic-sensitive-short'
        try:
            require_jwt_secret({'JWT_SECRET': value})
        except RuntimeError as error:
            self.assertNotIn(value, str(error))
        else:
            self.fail('Short signing secret should be rejected')

    def test_actual_api_startup_refuses_unsafe_sqlite_configuration(self):
        directory = Path(__file__).parent
        for value in (None, 'short', 'replace-with-a-long-random-secret', 'synthetic-startup-only-signing-key-not-production'):
            env = isolated_startup_environment(directory, os.environ)
            if value is not None:
                env['JWT_SECRET'] = value
            result = subprocess.run([sys.executable, '-c', 'import main; print("STARTUP_OK")'],
                                    cwd=directory, env=env, capture_output=True, text=True, timeout=30)
            if value is not None and value.startswith('synthetic-startup-'):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('STARTUP_OK', result.stdout)
            else:
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Set JWT_SECRET', result.stderr)
                if value:
                    self.assertNotIn(value, result.stderr)
