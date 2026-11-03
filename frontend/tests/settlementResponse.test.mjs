import test from 'node:test';
import assert from 'node:assert/strict';
import { verifySettlementResponse } from '../src/settlementResponse.js';
import { createPostingRequest } from '../src/postingRequest.js';

for (const family of ['advance', 'credit']) for (const action of ['apply', 'refund']) for (const paymentKind of ['payment_in', 'payment_out']) {
  test(`${family} ${paymentKind} ${action} requires a matching posted acknowledgement before unlocking`, async () => {
    const expected = { family, action, paymentKind, sourceId: 'source', body: {
      date: '2026-11-03', amount: '100', data: { applied_to: 'target', payment_account: 'bank', bank_account_id: 'bank-1' },
    } };
    // Shapes match all eight local FastAPI response variants, including the
    // absence of payment_kind in customer/supplier credit refund responses.
    const kind = family === 'advance' ? action === 'apply' ? 'advance_application' : 'advance_refund'
      : action === 'apply' ? 'credit_application' : paymentKind === 'payment_in' ? 'customer_refund' : 'supplier_refund';
    const sourceField = family === 'advance' ? 'advance_id' : 'credit_note_id';
    const valid = { id: 'posted-record', kind, date: expected.body.date, amount: '100.00', posted: true, data: {
      [sourceField]: expected.sourceId,
      ...(family === 'advance' || action === 'apply' ? { payment_kind: paymentKind } : {}),
      ...(action === 'apply' ? { applied_to: 'target' } : { payment_account: 'bank', bank_account_id: 'bank-1' }),
    } };
    const invalid = [null, {}, [], { ...valid, id: '' }, { ...valid, id: 'null' }, { ...valid, posted: undefined }, { ...valid, posted: false },
      { ...valid, posted: 'true' }, { ...valid, kind: 'payment_in' }, { ...valid, date: '2026-11-04' },
      ...['', null, 'NaN', 'Infinity', '-100', '99.99', '100.01'].map(amount => ({ ...valid, amount })),
      { ...valid, data: null }, { ...valid, data: { ...valid.data, [sourceField]: 'wrong-source' } },
      ...(action === 'apply' ? [{ ...valid, data: { ...valid.data, applied_to: 'wrong-target' } }]
        : [{ ...valid, data: { ...valid.data, payment_account: 'cash' } }, { ...valid, data: { ...valid.data, bank_account_id: 'wrong-bank' } }]),
      ...(family === 'advance' || action === 'apply' ? [{ ...valid, data: { ...valid.data, payment_kind: 'wrong-side' } }] : []),
    ];
    const posting = createPostingRequest();
    let response;
    const original = async () => verifySettlementResponse(response, expected);
    for (response of invalid) {
      await assert.rejects(posting.run(original), /could not be verified/);
      assert.equal(posting.pending, true);
    }
    response = valid;
    assert.deepEqual(await posting.run(() => assert.fail('Do not replace original command')), { value: valid });
    assert.equal(posting.pending, false);
    assert.equal(verifySettlementResponse({ ...valid, amount: '1e2' }, expected).amount, '1e2');
    for (const [entered, confirmed] of [['.5', '0.50'], ['+.5', '0.50'], ['.5e1', '5.00'], ['+.5E+1', '5.00'], ['5.', '5.00'], ['000.50', '0.50'], ['0.5000', '0.50'], ['.5e0', '0.50'], ['0'.repeat(150) + '.50', '0.50'], ['0.5' + '0'.repeat(150), '0.50']]) {
      const decimalExpected = { ...expected, body: { ...expected.body, amount: entered } };
      assert.equal(verifySettlementResponse({ ...valid, amount: confirmed }, decimalExpected).posted, true);
    }
    const precise = { ...expected, body: { ...expected.body, amount: '9007199254740993.01' } };
    assert.equal(verifySettlementResponse({ ...valid, amount: '9007199254740993.0100' }, precise).posted, true);
    assert.throws(() => verifySettlementResponse({ ...valid, amount: '9007199254740993.02' }, precise));
  });
}
