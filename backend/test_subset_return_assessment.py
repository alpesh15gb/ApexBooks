"""Assessment proofs only: no subset reconciliation algorithm is enabled here."""
import copy
import unittest
from decimal import Decimal as D
import test_completion


class SubsetReturnAssessmentTest(unittest.TestCase):
    context = test_completion.CompletionTest.client_context

    def source(self, lines, interstate=False):
        c, h, b = self.context('regular')
        state = '27' if interstate else '36'
        result = c.post(b+'/records', headers=h, json={
            'kind': 'purchase_bill', 'name': 'Proof supplier', 'date': '2026-04-01',
            'data': {'place_of_supply': state, 'supplier_state': '36', 'lines': lines}})
        self.assertEqual(result.status_code, 200, result.text)
        return c, h, b, result.json(), state

    def note(self, source, state, lines):
        return {'kind': 'debit_note', 'name': source['name'], 'date': '2026-04-02',
                'data': {'applied_to': source['id'], 'place_of_supply': state,
                         'supplier_state': '36', 'lines': lines}}

    def assert_rejected_without_mutation(self, c, h, b, note):
        before = c.get(b+'/journals', headers=h).json()
        records = c.get(b+'/records', headers=h).json()
        for route in ('/documents/preview', '/records'):
            result = c.post(b+route, headers=h, json=note)
            self.assertEqual(result.status_code, 422, result.text)
        self.assertEqual(c.get(b+'/journals', headers=h).json(), before)
        self.assertEqual(c.get(b+'/records', headers=h).json(), records)

    def test_same_class_lines_have_two_indistinguishable_head_allocations(self):
        lines = [{'description': name, 'quantity': 1, 'rate': '.06', 'gst_rate': 18,
                  'itc_treatment': 'pending_review'} for name in ('Unique A', 'Unique B')]
        c, h, b, source, state = self.source(lines)
        data = source['data']
        self.assertEqual([D(line['tax']) for line in data['lines']], [D('.01')]*2)
        self.assertEqual((D(data['cgst']), D(data['sgst'])), (D('.01'), D('.01')))
        self.assertTrue(all(not {'cgst', 'sgst', 'pending_input_cgst', 'pending_input_sgst'}.intersection(line)
                            for line in data['lines']))
        solutions = []
        for a_c in (D(0), D('.01')):
            a_s = D('.01')-a_c
            b_c, b_s = D(data['cgst'])-a_c, D(data['sgst'])-a_s
            if min(a_s, b_c, b_s) >= 0 and b_c+b_s == D('.01'):
                solutions.append(((a_c, a_s), (b_c, b_s)))
        self.assertEqual(len(set(solutions)), 2)
        first = c.post(b+'/records', headers=h, json=self.note(source, state, [lines[0]]))
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(D(first.json()['amount']), D('.07'))
        self.assert_rejected_without_mutation(c, h, b, self.note(source, state, [lines[1]]))

    def test_unique_pending_group_has_safe_arithmetic_witness_but_api_stays_closed(self):
        lines = [dict(description='Pending A', quantity=2, rate=100, gst_rate=18,
                      discount_amount=10, price_includes_tax=True, itc_treatment='pending_review'),
                 dict(description='Blocked B', quantity=2, rate=50, gst_rate=18,
                      discount_amount=4, price_includes_tax=True, itc_treatment='ineligible')]
        c, h, b, source, state = self.source(lines)
        note = self.note(source, state, [{**lines[0], 'quantity': 1, 'discount_amount': 5}])
        first = c.post(b+'/records', headers=h, json=note)
        self.assertEqual(first.status_code, 200, first.text)
        prior = first.json()['data']; original = source['data']
        residual = {head: D(original['pending_input_'+head])-D(prior['pending_input_'+head])
                    for head in ('cgst', 'sgst')}
        self.assertEqual(residual, {'cgst': D('7.24'), 'sgst': D('7.25')})
        self.assertEqual(sum(residual.values()), D(prior['lines'][0]['tax']))
        # Sole pending line identifies its category heads. The other line's
        # complementary budget remains intact; this is not permission to post it.
        for head in residual:
            blocked = D(original[head])-D(original['pending_input_'+head])
            self.assertEqual(blocked, D('7.32'))
            self.assertEqual(D(prior[head])+residual[head]+blocked, D(original[head]))
        self.assert_rejected_without_mutation(c, h, b, note)

    def test_existing_history_can_make_remaining_pending_head_impossible(self):
        lines = [dict(description='Pending penny', quantity=2, rate='.02', gst_rate=18,
                      itc_treatment='pending_review'),
                 dict(description='Blocked penny', quantity=2, rate='.03', gst_rate=18,
                      itc_treatment='ineligible')]
        c, h, b, source, state = self.source(lines)
        note = self.note(source, state, [{**line, 'quantity': 1} for line in lines])
        first = c.post(b+'/records', headers=h, json=note)
        self.assertEqual(first.status_code, 200, first.text)
        residual = {key: D(source['data'][key])-D(first.json()['data'][key])
                    for key in ('cgst', 'sgst', 'pending_input_cgst', 'pending_input_sgst')}
        self.assertGreater(residual['pending_input_cgst'], residual['cgst'])
        self.assert_rejected_without_mutation(c, h, b, note)

    def test_single_igst_head_has_no_split_ambiguity_and_ordinary_subset_can_finish(self):
        lines = [{'description': name, 'quantity': 1, 'rate': '.06', 'gst_rate': 18,
                  'itc_treatment': 'pending_review'} for name in ('Unique A', 'Unique B')]
        c, h, b, source, state = self.source(lines, interstate=True)
        original = copy.deepcopy(source)
        self.assertEqual((D(source['data']['cgst']), D(source['data']['sgst']), D(source['data']['igst'])),
                         (D(0), D(0), D('.02')))
        saved = []
        for line in reversed(lines):
            note = self.note(source, state, [line])
            preview = c.post(b+'/documents/preview', headers=h, json=note)
            result = c.post(b+'/records', headers=h, json=note)
            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['amount'], preview.json()['amount'])
            self.assertEqual(D(result.json()['data']['igst']), D(result.json()['data']['lines'][0]['tax']))
            self.assertNotIn('return_rounding', result.json()['data'])
            saved.append(result.json())
        self.assertEqual(sum(D(row['amount']) for row in saved), D(source['amount']))
        self.assertEqual(sum(D(row['data']['pending_input_igst']) for row in saved), D(source['data']['pending_input_igst']))
        current = c.get(b+'/records/'+source['id'], headers=h).json()
        self.assertEqual(current['data']['lines'], original['data']['lines'])
