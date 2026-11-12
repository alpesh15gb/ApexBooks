import test from 'node:test';
import assert from 'node:assert/strict';
import { dashboardWork, recentTransactions } from '../src/dashboardModel.js';

test('attention work excludes cancellations and keeps current dues independent of reporting period', () => {
  const invoice = { kind: 'sales_invoice', posted: true, amount: '100', outstanding: '60', date: '2025-01-01', data: { due_date: '2025-02-01' } };
  const records = [invoice, { ...invoice, cancelled: true }, { ...invoice, data: { ...invoice.data, cancelled: true } }, { ...invoice, posted: false }, { ...invoice, outstanding: '0' }, { ...invoice, data: { due_date: '2026-12-01' } }, { kind: 'purchase_bill', posted: true, outstanding: '20' }, { kind: 'estimate' }, { kind: 'estimate', converted_to: 'INV-1' }, { kind: 'estimate', cancelled: true }];
  const work = dashboardWork(records, '2026-11-12');
  assert.equal(work.overdue.length, 1);
  assert.equal(work.openBills.length, 1);
  assert.equal(work.quotes.length, 1);
});

test('recent activity sorts by business date and creation time without mutating loaded records', () => {
  const records = [{ id: 'old', kind: 'sales_invoice', date: '2026-01-01' }, { id: 'master', kind: 'party', date: '2026-11-12' }, { id: 'late', kind: 'expense', date: '2026-11-10', data: { created_at: '2026-11-10T15:00:00' } }, { id: 'early', kind: 'sales_invoice', date: '2026-11-10', data: { created_at: '2026-11-10T09:00:00' } }];
  assert.deepEqual(recentTransactions(records).map(r => r.id), ['late', 'early', 'old']);
  assert.equal(records[0].id, 'old');
});
