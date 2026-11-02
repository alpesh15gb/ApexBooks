import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequestScope } from '../src/requestScope.js';

test('only the newest same-company refresh can update records', () => {
  const scope = createRequestScope('company-a');
  const old = scope.latest();
  const current = scope.latest();
  assert.equal(old(), false);
  assert.equal(current(), true);
});
test('switching away and back cannot revive an old request or save', () => {
  const scope = createRequestScope('company-a');
  const save = scope.capture();
  const request = scope.latest();
  scope.setContext('company-b');
  scope.setContext('company-a');
  assert.equal(save(), false);
  assert.equal(request(), false);
  assert.equal(scope.capture()(), true);
});
test('a refresh does not invalidate an in-flight same-company save', () => {
  const scope = createRequestScope('company-a');
  const save = scope.capture();
  scope.latest();
  scope.setContext('company-a');
  assert.equal(save(), true);
});
