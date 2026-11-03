"""Target-guard tests: mock Docker completely; no host credentials or DB access."""
import copy
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("backup_target", Path(__file__).with_name("check_backup_target.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CONFIG = {"services": {
    "db": {"image": "postgres:16-alpine", "environment": {"POSTGRES_DB": "apex", "POSTGRES_USER": "apex"}},
    "api": {"environment": {"DATABASE_URL": "postgresql+psycopg://apex:synthetic@db:5432/apex"}},
}}


class TargetGuardTest(unittest.TestCase):
    def test_timer_units_require_operator_environment_without_auto_optin(self):
        import configparser
        for name in ("apex-backup.service", "apex-secure-backup.service"):
            unit = configparser.ConfigParser(interpolation=None)
            unit.read(Path(__file__).with_name(name))
            self.assertEqual(unit["Service"]["EnvironmentFile"], "/etc/apex-books/backup.env")
            self.assertNotIn("Environment", unit["Service"])
        # An unconfigured service has no reviewed scope, and must not invoke Docker.
        with patch.dict(os.environ, {}, clear=True), patch.object(module.subprocess, "run") as run, redirect_stderr(io.StringIO()):
            self.assertEqual(module.main(), 1)
            run.assert_not_called()

    def test_reviewed_local_configuration(self):
        self.assertTrue(module.valid_config(CONFIG))

    def test_external_or_ambiguous_urls(self):
        for url in [None, "", "postgresql://apex:secret@provider.example/apex", "postgresql://apex@db/other",
                    "postgresql://other@db/apex", "postgresql://apex@db:9999/apex",
                    "postgresql://apex@db/apex?host=external", "postgresql://apex@db/apex#other",
                    "postgresql://apex@db:bad/apex", "sqlite:///apex"]:
            with self.subTest(url=url):
                self.assertFalse(module.local_database(url))

    def test_config_identity_and_network_guards(self):
        for field, value in [("image", "custom-postgres:latest"), ("network_mode", "host"),
                             ("environment", {"POSTGRES_DB": "other", "POSTGRES_USER": "apex"})]:
            config = copy.deepcopy(CONFIG)
            config["services"]["db"][field] = value
            self.assertFalse(module.valid_config(config))
        config = copy.deepcopy(CONFIG)
        del config["services"]["db"]
        self.assertFalse(module.valid_config(config))
        config = copy.deepcopy(CONFIG)
        config["services"]["api"]["extra_hosts"] = ["db:203.0.113.1"]
        self.assertFalse(module.valid_config(config))
        config = copy.deepcopy(CONFIG)
        config["networks"] = {"default": {"external": True}}
        self.assertFalse(module.valid_config(config))

    def test_explicit_scope_required_before_any_docker_call(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(module.subprocess, "run") as run, redirect_stderr(io.StringIO()):
            self.assertEqual(module.main(), 1)
            run.assert_not_called()

    def test_only_config_and_running_api_probe_on_success(self):
        import json
        with patch.dict(os.environ, {"APEX_BACKUP_SCOPE": "compose-local"}), patch.object(module.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(CONFIG).encode())) as run:
            self.assertEqual(module.main(), 0)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args_list[0].args[0], ["docker", "compose", "config", "--format", "json"])
            self.assertEqual(run.call_args_list[1].args[0][:7], ["docker", "compose", "exec", "-T", "api", "python", "-c"])

    def test_no_secrets_in_failure_output(self):
        import json
        error = io.StringIO()
        for result in [b'not-json-private-password', json.dumps({"services": {}}).encode()]:
            with patch.dict(os.environ, {"APEX_BACKUP_SCOPE": "compose-local"}), patch.object(module.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, result)) as run, redirect_stderr(error):
                self.assertEqual(module.main(), 1)
                self.assertEqual(run.call_count, 1)
        self.assertNotIn("private-password", error.getvalue())

    def test_running_api_mismatch_fail_closed(self):
        import json
        error = io.StringIO()
        with patch.dict(os.environ, {"APEX_BACKUP_SCOPE": "compose-local"}), patch.object(module.subprocess, "run", side_effect=[subprocess.CompletedProcess([], 0, json.dumps(CONFIG).encode()), subprocess.CalledProcessError(1, "probe", stderr=b"private-password")]), redirect_stderr(error):
            self.assertEqual(module.main(), 1)
        self.assertNotIn("private-password", error.getvalue())

    def test_running_probe_has_same_url_rules(self):
        for url, expected in [(CONFIG["services"]["api"]["environment"]["DATABASE_URL"], 0),
                              ("postgresql://apex:private@external/apex", 1),
                              ("postgresql://apex@db/apex?host=external", 1)]:
            # Only a local Python subprocess; never invokes Docker or a database.
            result = subprocess.run([os.sys.executable, "-c", module.RUNTIME_CHECK], env={"DATABASE_URL": url}, capture_output=True)
            self.assertEqual(result.returncode, expected)
            self.assertEqual(result.stdout + result.stderr, b"")


if __name__ == "__main__":
    unittest.main()
