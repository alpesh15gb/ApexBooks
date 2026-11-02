import test from 'node:test';
import assert from 'node:assert/strict';
import { compareRegisterRecords } from '../src/registerOrder.js';

const rows = [
  { id: 'z', date: '2026-11-01', number: 'QA-OCR-M02', amount: 1180, outstanding: 540, data: { created_at: '2026-11-01T10:00:00+00:00' } },
  { id: 'a', date: '2026-11-01', number: 'BILL/26-27/0001', amount: 118, outstanding: 68, data: { created_at: '2026-11-01T11:00:00+00:00' } },
  { id: 'zz', date: '2026-11-01', number: 'LEGACY-999', amount: 118, outstanding: 68, data: {} },
  { id: 'backdated', date: '2026-10-31', number: 'NEW-999', amount: 118, data: { created_at: '2026-11-01T12:00:00+00:00' } },
];

test('same-day creation time wins over reference text and random IDs', () => {
  assert.deepEqual([...rows].sort(compareRegisterRecords).map(r => r.id), ['a', 'z', 'zz', 'backdated']);
});

test('oldest reverses full chronology including legacy records', () => {
  assert.deepEqual([...rows].sort((a, b) => compareRegisterRecords(a, b, 'oldest')).map(r => r.id), ['backdated', 'zz', 'z', 'a']);
});

test('amount and balance ranking use chronology for equal values', () => {
  for (const order of ['amount', 'balance']) {
    assert.deepEqual([...rows].sort((a, b) => compareRegisterRecords(a, b, order)).slice(0, 3).map(r => r.id), ['z', 'a', 'zz']);
  }
});
