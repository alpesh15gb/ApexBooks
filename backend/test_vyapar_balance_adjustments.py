"""Vyapar cash and bank "adjust balance" entries resolve from their type, without asking."""
import unittest
from decimal import Decimal
import test_vyapar_expanded as expanded
from test_vyapar_posting import fixture
from vyapar_posting import posting_plan

Base = expanded.ExpandedVyaparTests


def cash(id_, type_, amount, description='Synthetic'):
    return {'cash_adj_id': id_, 'cash_adj_type': type_, 'cash_adj_amount': amount, 'cash_adj_date': '2026-03-02 01:33:15', 'cash_adj_description': description}


def bank(id_, type_, amount, description='Synthetic'):
    return {'bank_adj_id': id_, 'bank_adj_bank_id': 3, 'bank_adj_type': type_, 'bank_adj_amount': amount, 'bank_adj_date': '2026-03-02 01:31:53', 'bank_adj_description': description, 'bank_adj_to_bank_id': None}


class BalanceAdjustmentTests(unittest.TestCase):
    client = Base.client
    post = Base.post
    roundtrip = Base.roundtrip

    def test_types_set_the_direction_of_each_balance(self):
        base = posting_plan(fixture())['bank_movement']
        t = fixture()
        t['kb_cash_adjustments'] = [cash(1, 20, 300), cash(2, 19, 40)]
        t['kb_bank_adjustments'] = [bank(1, 18, 70), bank(2, 17, 5.35)]
        plan = posting_plan(t)
        self.assertTrue(plan['ready'], plan['errors'])
        self.assertEqual(Decimal(plan['bank_movement']['1']) - Decimal(base.get('1', '0')), Decimal('-260'))
        self.assertEqual(Decimal(plan['bank_movement']['3']) - Decimal(base.get('3', '0')), Decimal('-64.65'))

    def test_posting_reconciles_and_stays_out_of_profit(self):
        t = fixture()
        t['kb_cash_adjustments'] = [cash(1, 20, 300)]
        t['kb_bank_adjustments'] = [bank(1, 18, 70), bank(2, 17, 5.35)]
        before = self.post(fixture())
        report = lambda c, h, b: c.get(b + '/reports/financial', headers=h, params={'from_date': '2026-01-01', 'to_date': '2026-12-31'}).json()
        c, h, b, records = self.post(t)
        self.assertEqual(report(c, h, b)['net_profit'], report(*before[:3])['net_profit'])
        self.assertEqual(Decimal(report(c, h, b)['balance_difference']), 0)
        rows = {r['number']: r for r in records if r['kind'] == 'balance_adjustment'}
        self.assertEqual(set(rows), {'VYP-ADJ-CASH-1', 'VYP-ADJ-BANK-1', 'VYP-ADJ-BANK-2'})
        self.assertEqual(rows['VYP-ADJ-CASH-1']['data']['direction'], 'decrease')
        self.assertEqual(rows['VYP-ADJ-BANK-2']['data']['direction'], 'increase')
        self.assertTrue(all(check['passed'] for check in self.posting_result['reconciliation']))
        self.roundtrip(c, h, b)

    def test_preview_says_what_was_applied_and_the_closing_balances(self):
        t = fixture()
        t['kb_cash_adjustments'] = [cash(1, 20, 300, 'Clearing cash')]
        warnings = ' | '.join(posting_plan(t)['warnings'])
        self.assertIn('Cash adjustment 1 on 2026-03-02 (Clearing cash): reduced ₹300.00 automatically', warnings)
        self.assertIn('Closing balances after these adjustments', warnings)

    def test_zero_amount_posts_nothing(self):
        t = fixture()
        t['kb_cash_adjustments'] = [cash(1, 20, 0)]
        plan = posting_plan(t)
        self.assertTrue(plan['ready'], plan['errors'])
        self.assertEqual(plan['financial_events'], [])

    def test_unknown_or_invalid_entries_still_block(self):
        for name, table, row in (
                ('unknown cash type', 'kb_cash_adjustments', cash(1, 99, 10)),
                ('unknown bank type', 'kb_bank_adjustments', bank(1, 99, 10)),
                ('negative', 'kb_cash_adjustments', cash(1, 20, -10)),
                ('bad date', 'kb_bank_adjustments', {**bank(1, 18, 10), 'bank_adj_date': 'not-a-date'}),
                ('bank type on a transfer', 'kb_bank_adjustments', {**bank(1, 18, 10), 'bank_adj_to_bank_id': 3})):
            with self.subTest(name):
                t = fixture()
                t[table] = [row]
                self.assertFalse(posting_plan(t)['ready'])


if __name__ == '__main__':
    unittest.main()
