// Synthetic React refresh-progress benchmark; not a browser/device timing claim.
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';
import { performance } from 'node:perf_hooks';
import assert from 'node:assert/strict';
import { selectRegisterRecords, useRegisterRecords } from '../src/registerSelection.js';
const dom = new JSDOM('<div id="root"></div>');
Object.assign(globalThis, { window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true });
let reads = 0;
const records = Array.from({ length: 30000 }, (_, i) => ({ id: String(i), get kind() { reads++; return 'sales_invoice'; }, name: `Party ${i % 400}`, number: `INV-${i}`, date: `2026-10-${String(i % 28 + 1).padStart(2, '0')}`, amount: String(i % 1000), outstanding: '10', posted: true, data: {} }));
const options = { companyId: 'synthetic-a', records, page: 'sales_invoice', query: { from: '', to: '', party: '', sort: 'newest' }, search: '', activeRegisterFilter: 'all', asOf: '2026-11-03' };
async function run(memoized) {
  reads = 0; let result;
  function Probe({ progress }) { result = memoized ? useRegisterRecords(options) : selectRegisterRecords(options); return React.createElement('span', null, progress); }
  const root = createRoot(document.getElementById('root')); const start = performance.now();
  for (let progress = 0; progress <= 60; progress++) await act(async () => root.render(React.createElement(Probe, { progress })));
  const elapsed = performance.now() - start; const visits = reads;
  await act(async () => root.unmount());
  return { elapsed, visits, ids: result.filtered.map(row => row.id) };
}
const before = await run(false); const after = await run(true);
assert.deepEqual(after.ids, before.ids);
assert.equal(before.visits, 30000 * 61); assert.equal(after.visits, 30000);
console.log(JSON.stringify({ rows: records.length, refreshProgressRenders: 61, beforeMs: +before.elapsed.toFixed(2), afterMs: +after.elapsed.toFixed(2), beforeRowVisits: before.visits, afterRowVisits: after.visits, orderedIdsEqual: true }));
dom.window.close();
