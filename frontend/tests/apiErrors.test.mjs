import test from 'node:test';
import assert from 'node:assert/strict';
import { apiErrorMessage } from '../src/apiErrors.js';

test('service failure is not presented as an input mistake or leaked internal detail', () => {
  const message = apiErrorMessage(500, { detail: 'private-internal-stack' });
  assert.match(message, /temporarily unavailable/);
  assert.doesNotMatch(message, /private-internal|check your details/);
});
test('uncertain mutations explain same-save recovery, reads do not suggest posting', () => {
  assert.match(apiErrorMessage(0, {}, true), /same save/);
  assert.match(apiErrorMessage(408, {}, true), /same save/);
  assert.doesNotMatch(apiErrorMessage(503), /transaction/);
});
test('validation and permission errors remain actionable', () => {
  assert.equal(apiErrorMessage(422, { detail: [{ msg: 'Quantity must be positive' }] }), 'Quantity must be positive');
  assert.equal(apiErrorMessage(403, { detail: 'Owner access required' }), 'Owner access required');
  assert.match(apiErrorMessage(429), /wait/);
});
