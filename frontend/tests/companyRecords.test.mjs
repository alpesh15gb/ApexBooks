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
    return Array.from({ length: 500 }, (_, id) => ({ id }));
  }, 'company'), /Network interrupted/);
});
