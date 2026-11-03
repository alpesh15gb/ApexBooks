import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';
import { selectRegisterRecords, useRegisterRecords } from '../src/registerSelection.js';
const dom = new JSDOM('<div id="root"></div>');
Object.assign(globalThis, { window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true });
after(() => dom.window.close());
const row = (id, extra = {}) => ({ id, kind: 'sales_invoice', name: 'Buyer', number: `INV-${id}`, date: '2026-11-02', posted: true, amount: '100', outstanding: '50', data: { due_date: '2026-11-02' }, ...extra });
const base = { companyId: 'company-a', records: [row('a'), row('b', { outstanding: '0' }), row('c', { name: 'Other', date: '2026-10-01', posted: false })], page: 'sales_invoice', query: { from: '', to: '', party: '', sort: 'newest' }, search: '', activeRegisterFilter: 'all', asOf: '2026-11-03' };
const ids = value => value.filtered.map(row => row.id);
test('selection preserves dates, party, search, status, ordering and source array', () => {
  const original = [...base.records];
  assert.deepEqual(ids(selectRegisterRecords(base)), ['b', 'a', 'c']);
  assert.deepEqual(ids(selectRegisterRecords({ ...base, activeRegisterFilter: 'unpaid' })), ['a']);
  assert.deepEqual(ids(selectRegisterRecords({ ...base, activeRegisterFilter: 'paid' })), ['b']);
  assert.deepEqual(ids(selectRegisterRecords({ ...base, activeRegisterFilter: 'overdue' })), ['a']);
  assert.deepEqual(ids(selectRegisterRecords({ ...base, activeRegisterFilter: 'unposted' })), ['c']);
  assert.deepEqual(ids(selectRegisterRecords({ ...base, search: 'iNv-A' })), ['a']);
  assert.deepEqual(ids(selectRegisterRecords({ ...base, query: { from: '2026-11-01', to: '2026-11-03', party: 'Buyer', sort: 'oldest' } })), ['a', 'b']);
  assert.deepEqual(base.records, original);
  const masters = [row('x', { kind: 'item', data: { is_active: false } }), row('y', { kind: 'item' })];
  assert.deepEqual(ids(selectRegisterRecords({ ...base, records: masters, page: 'item', activeRegisterFilter: 'active', query: { from: '2099-01-01' } })), ['y']);
  assert.deepEqual(ids(selectRegisterRecords({ ...base, records: masters, page: 'item', activeRegisterFilter: 'inactive' })), ['x']);
});
test('progress-only renders do not rescan; all workspace/filter/data/day inputs invalidate', async () => {
  let result; let count = 0;
  const records = base.records.map(item => ({ ...item, get kind() { count++; return item.kind; } }));
  function Probe({ options, progress }) { result = useRegisterRecords(options); return React.createElement('span', null, progress); }
  const root = createRoot(document.getElementById('root'));
  let options = { ...base, records };
  const render = progress => act(async () => root.render(React.createElement(Probe, { options, progress })));
  try {
    await render(0); const first = result;
    for (let i = 1; i <= 60; i++) { options = { ...options, query: { ...options.query } }; await render(i); assert.equal(result, first); }
    assert.equal(count, 3);
    for (const change of [{ companyId: 'company-b' }, { search: 'INV-a' }, { activeRegisterFilter: 'overdue' }, { asOf: '2026-11-02' }, { query: { ...base.query, from: '2026-11-01' } }, { query: { ...base.query, to: '2026-11-01' } }, { query: { ...base.query, party: 'Other' } }, { query: { ...base.query, sort: 'oldest' } }, { page: 'item' }, { records: [...records] }]) {
      const previous = result; options = { ...base, records, ...change }; await render(100); assert.notEqual(result, previous); assert.deepEqual(ids(result), ids(selectRegisterRecords(options)));
    }
    options = { ...base, companyId: '', records: [] }; await render(101); assert.deepEqual(ids(result), []);
  } finally { await act(async () => root.unmount()); }
});
