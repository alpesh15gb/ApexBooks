import test from 'node:test';
import assert from 'node:assert/strict';
import { fetchCompanyRecords, COMPANY_PAGE_SIZE } from '../src/companyRecords.js';

test('1,001 company rows require three bounded requests rather than eleven', async () => {
  const source = Array.from({ length: 1001 }, (_, id) => ({ id: String(id) }));
  const requests = [], progress = [];
  const rows = await fetchCompanyRecords(async path => {
    const params = new URL(path, 'http://localhost').searchParams;
    requests.push(path);
    assert.equal(Number(params.get('limit')), 500);
    return source.slice(Number(params.get('offset')), Number(params.get('offset')) + COMPANY_PAGE_SIZE);
  }, 'synthetic-company', { onProgress: value => progress.push(value) });
  assert.deepEqual(rows, source);
  assert.equal(requests.length, 3);
  assert.deepEqual(progress, [500, 1000, 1001]);
});

test('switching company aborts obsolete pagination and never publishes partial books', async () => {
  let current = true, calls = 0;
  const result = await fetchCompanyRecords(async () => {
    calls++;
    current = false;
    return Array.from({ length: 500 }, () => ({ id: 'old-company' }));
  }, 'old-company', { isCurrent: () => current });
  assert.equal(result, null);
  assert.equal(calls, 1);
});

test('cancelled fetch does not start network requests and error propagates without partial success', async () => {
  const abort = new AbortController();
  abort.abort();
  assert.equal(await fetchCompanyRecords(() => { throw new Error('must not fetch'); }, 'company', { signal: abort.signal }), null);
  let calls = 0;
  await assert.rejects(fetchCompanyRecords(async () => {
    if (++calls === 2) throw new Error('Network interrupted');
    return Array.from({ length: 500 }, (_, id) => ({ id: String(id) }));
  }, 'company'), /Network interrupted/);
});

test('a concurrent insert restarts the scan rather than publishing duplicate financial rows', async () => {
  const source = Array.from({ length: 1001 }, (_, id) => ({ id: String(id), amount: '100.00' }));
  const offsets = [], progress = [];
  let inserted = false;
  const result = await fetchCompanyRecords(async path => {
    const offset = Number(new URL(path, 'http://localhost').searchParams.get('offset'));
    offsets.push(offset);
    if (offset === 500 && !inserted) {
      source.unshift({ id: 'new-invoice', amount: '250.00' });
      inserted = true;
    }
    return source.slice(offset, offset + COMPANY_PAGE_SIZE);
  }, 'synthetic', { onProgress: value => progress.push(value) });
  assert.deepEqual(offsets, [0, 500, 0, 500, 1000]);
  assert.deepEqual(result, source);
  assert.equal(new Set(result.map(row => row.id)).size, result.length);
  assert.equal(result.reduce((sum, row) => sum + Number(row.amount), 0), 100350);
  assert.ok(progress.includes(0), 'restart resets partial progress');
});

test('repeated overlapping pages stop after one retry without publishing partial books', async () => {
  let calls = 0;
  const batch = Array.from({ length: 500 }, (_, id) => ({ id: String(id) }));
  await assert.rejects(fetchCompanyRecords(async () => { calls++; return batch; }, 'synthetic'), /Company data changed while loading/);
  assert.equal(calls, 4);
});

test('company change during an overlapping response does not restart the obsolete scan', async () => {
  let current = true, calls = 0;
  const batch = Array.from({ length: 500 }, (_, id) => ({ id: String(id) }));
  const result = await fetchCompanyRecords(async () => {
    if (++calls === 2) current = false;
    return batch;
  }, 'old-company', { isCurrent: () => current });
  assert.equal(result, null);
  assert.equal(calls, 2);
});

for (const [name, malformed] of [
  ['oversized page', Array.from({ length: 501 }, (_, i) => ({ id: String(i) }))],
  ['array row', [[]]], ['object instead of page', {}], ['string instead of page', 'bad'],
  ['null row', [null]], ['primitive row', [42]], ['missing id', [{}]],
  ['numeric id', [{ id: 123 }]], ['empty id', [{ id: '' }]], ['blank id', [{ id: '  ' }]],
]) test(`reject malformed company page: ${name}`, async () => {
  let progress = 0;
  await assert.rejects(fetchCompanyRecords(async () => malformed, 'synthetic', { onProgress: () => progress++ }), /invalid company records/i);
  assert.equal(progress, 0, 'invalid page is not counted as loaded');
});

test('invalid later page rejects complete scan without returning partial records', async () => {
  let calls = 0;
  await assert.rejects(fetchCompanyRecords(async () => ++calls === 1
    ? Array.from({ length: 500 }, (_, i) => ({ id: String(i) }))
    : [{ name: 'Missing identity' }], 'synthetic'), /invalid company records/i);
  assert.equal(calls, 2);
});

test('empty page is confirmed empty; valid IDs and future fields remain unchanged', async () => {
 assert.deepEqual(await fetchCompanyRecords(async()=>[], 'synthetic'), []);
 const rows=[{id:' exact identity ',kind:'future_kind',future_field:{value:true}}];
 assert.deepEqual(await fetchCompanyRecords(async()=>rows, 'synthetic'),rows);
});
