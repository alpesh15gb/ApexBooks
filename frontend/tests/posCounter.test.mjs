import assert from 'node:assert/strict';
import test from 'node:test';
import { counterTender, matchCounterProduct } from '../src/posCounter.js';

test('scans use exact barcodes and preserve leading zeroes', () => {
  const product = { name: 'Cable', data: { barcode: '001234' } };
  assert.equal(matchCounterProduct([product], ' 001234 ').item, product);
  assert.equal(matchCounterProduct([product], 'CABLE').item, product);
  assert.equal(matchCounterProduct([product], '1234').item, undefined);
  assert.equal(matchCounterProduct([product], 'Cab').item, undefined);
  assert.match(matchCounterProduct([product, { ...product }], '001234').message, /Multiple/);
});

test('split tender computes the cash share, shortage and change in exact paise', () => {
  assert.deepEqual(counterTender('123.45', 'split', '23.32', '110'), {
    cash: 10013, bank: 2332, tender: 11000, change: 987,
  });
  assert.deepEqual(counterTender('123.45', 'split', '23.32', ''), {
    cash: 10013, bank: 2332, tender: 10013, change: 0,
  });
  assert.equal(counterTender('123.45', 'split', '23.32', '100.12').change, -1);
  assert.equal(counterTender('123.45', 'split', '123.45', '100'), null);
  assert.equal(counterTender('123.45', 'split', '1.001', '100'), null);
  assert.equal(counterTender('0.00', 'cash', '', ''), null);
});
