"""Upgrade comparison normalizes only explicitly verified additive metadata."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('upgrade_rehearsal_comparison', Path(__file__).resolve().parents[1] / 'tests/upgrade/rehearse_legacy.py')
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)

class UpgradeMetadataTest(unittest.TestCase):
    def original(self):
        return {'party': {'data': {'phone': 'synthetic', 'is_active': False}},
                'balances': {'receivable': '100.00'},
                'transactions': [{'amount': '25.00', 'outstanding': '75.00'}]}

    def test_only_known_zero_and_null_metadata_is_normalized(self):
        original = self.original()
        current = copy.deepcopy(original)
        current['party']['data']['version'] = 0
        current['transactions'][0]['converted_to'] = None
        upgrade.normalize_legacy_statement_metadata(current)
        self.assertEqual(current, original)
        upgrade.normalize_legacy_statement_metadata(original)
        self.assertEqual(current, original)

    def test_nonzero_or_malformed_revision_and_real_conversion_fail(self):
        for value in (1, -1, False, None, '0', 0.0):
            with self.subTest(value=value):
                current = self.original()
                current['party']['data']['version'] = value
                with self.assertRaises(AssertionError):
                    upgrade.normalize_legacy_statement_metadata(current)
        current = self.original()
        current['transactions'][0]['converted_to'] = 'different-document'
        with self.assertRaises(AssertionError):
            upgrade.normalize_legacy_statement_metadata(current)

    def test_financial_or_other_master_changes_remain_visible(self):
        original = self.original()
        current = copy.deepcopy(original)
        current['balances']['receivable'] = '101.00'
        current['party']['data']['is_active'] = True
        upgrade.normalize_legacy_statement_metadata(current)
        self.assertNotEqual(current, original)
        self.assertEqual(current['balances']['receivable'], '101.00')
        self.assertTrue(current['party']['data']['is_active'])
