import test from 'node:test';
import assert from 'node:assert/strict';
import { setupSteps } from '../src/setupSteps.js';

test('setup steps track business, bank/UPI, parties, items and the first invoice', () => {
  const company = { tax_mode: 'regular', address: '', gstin: '' };
  const empty = setupSteps({ company, records: [], branding: {} });
  assert.deepEqual(empty.map(s => s.key), ['business', 'payment', 'party', 'item', 'invoice']);
  assert.equal(empty.filter(s => s.complete).length, 0);
  assert.equal(setupSteps({ company: { ...company, address: 'Shop 1' }, records: [], branding: {} })[0].complete, false); // GSTIN still missing
  assert.equal(setupSteps({ company: { tax_mode: 'unregistered', address: 'Shop 1' }, records: [], branding: {} })[0].complete, true);
  const full = setupSteps({ company: { ...company, address: 'Shop 1', gstin: '36AAAAA0000A1Z5' }, records: [{ kind: 'party' }, { kind: 'item' }, { kind: 'sales_invoice', posted: true }], branding: { upi_id: 'x@upi' } });
  assert.equal(full.every(s => s.complete), true);
  assert.equal(setupSteps({ company, records: [{ kind: 'sales_invoice', posted: false }], branding: {} })[4].complete, false);
});
