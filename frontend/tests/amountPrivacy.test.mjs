import test from 'node:test';
import assert from 'node:assert/strict';
import { MASKED_AMOUNT, amountText, readAmountsHidden, revealUnsupported, writeAmountsHidden } from '../src/amountPrivacy.js';

const memory = () => { const data = new Map(); return { getItem: key => data.has(key) ? data.get(key) : null, setItem: (key, value) => data.set(key, String(value)), removeItem: key => data.delete(key) }; };

test('amounts are visible until the user hides them, and the choice is remembered on the device', () => {
  const storage = memory();
  assert.equal(readAmountsHidden(storage), false);
  writeAmountsHidden(true, storage);
  assert.equal(readAmountsHidden(storage), true);
  writeAmountsHidden(false, storage);
  assert.equal(readAmountsHidden(storage), false);
});

test('storage that throws or is missing never hides amounts by accident or breaks the dashboard', () => {
  const broken = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); } };
  assert.equal(readAmountsHidden(broken), false);
  assert.doesNotThrow(() => writeAmountsHidden(true, broken));
  assert.doesNotThrow(() => writeAmountsHidden(false, null));
  assert.equal(readAmountsHidden(null), false);
});

test('hidden amounts show a fixed mask that does not reveal size or sign', () => {
  assert.equal(amountText(true, '₹98,76,543.21'), MASKED_AMOUNT);
  assert.equal(amountText(true, '-₹5.00'), MASKED_AMOUNT);
  assert.equal(amountText(false, '₹5.00'), '₹5.00');
  assert.ok(!/\d/.test(MASKED_AMOUNT));
});

test('only a missing endpoint lets the user reveal without a password check', () => {
  assert.equal(revealUnsupported({ status: 404 }), true);
  assert.equal(revealUnsupported({ status: 405 }), true);
  for (const status of [0, 401, 403, 422, 429, 500]) assert.equal(revealUnsupported({ status }), false);
  assert.equal(revealUnsupported(undefined), false);
});
