import test from 'node:test';
import assert from 'node:assert/strict';
import { relatedRecordActions, settlementLabel } from '../src/recordLifecycle.js';

test('posted open invoices expose settlement and linked return actions', () => {
  assert.deepEqual(relatedRecordActions({ kind: 'sales_invoice', posted: true, outstanding: '20' }, true).map(a => a.kind), ['payment_in', 'credit_note']);
  assert.deepEqual(relatedRecordActions({ kind: 'purchase_bill', posted: true, outstanding: '20' }, true).map(a => a.kind), ['payment_out', 'debit_note']);
  assert.deepEqual(relatedRecordActions({ kind: 'pos', posted: true }, true).map(a => a.kind), ['credit_note']);
});
test('viewers, unposted prototypes and settled documents cannot collect another payment', () => {
  const invoice = { kind: 'sales_invoice', posted: true, outstanding: '20' };
  assert.deepEqual(relatedRecordActions(invoice, false), []);
  assert.deepEqual(relatedRecordActions({ ...invoice, posted: false }, true), []);
  assert.deepEqual(relatedRecordActions({ ...invoice, outstanding: '0' }, true).map(a => a.kind), ['credit_note']);
});
test('settlement is distinct from posting and draft conversion', () => {
  assert.equal(settlementLabel({ kind: 'sales_invoice', posted: true, amount: '100', outstanding: '40' }), 'Part settled');
  assert.equal(settlementLabel({ kind: 'sales_invoice', posted: true, amount: '100', outstanding: '100' }), 'Unpaid');
  assert.equal(settlementLabel({ kind: 'sales_invoice', posted: true, amount: '100', outstanding: '0' }), 'Settled');
  assert.equal(settlementLabel({ kind: 'estimate', posted: false, outstanding: '0' }), '');
});
