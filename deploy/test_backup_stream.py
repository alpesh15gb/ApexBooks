"""Synthetic binary pipeline validation; no database or remote access."""
from pathlib import Path
import subprocess
import sys
import unittest


class BackupStreamTest(unittest.TestCase):
    def run_stream(self, content):
        return subprocess.run([sys.executable, str(Path(__file__).with_name('require_nonempty_stream.py'))], input=content, capture_output=True, timeout=10)

    def test_empty_stream_rejected(self):
        result = self.run_stream(b'')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'')
        self.assertIn(b'backup stream was empty', result.stderr)

    def test_binary_stream_preserved_across_chunks(self):
        content = bytes(range(256)) * 9000
        result = self.run_stream(content)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, content)

    def test_single_byte_not_lost(self):
        result = self.run_stream(b'\x00')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'\x00')
