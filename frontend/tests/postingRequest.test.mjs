import test from 'node:test';
import assert from 'node:assert/strict';
import { createPostingRequest } from '../src/postingRequest.js';

test('an uncertain save replays its original operation rather than an edited request', async () => {
  const posting = createPostingRequest();
  let calls = 0;
  const original = async () => { if (++calls === 1) throw new TypeError('Network interrupted'); return 'saved-original'; };
  await assert.rejects(posting.run(original));
  assert.equal(posting.pending, true);
  assert.deepEqual(await posting.run(async () => assert.fail('Must not post a changed payload')), { value: 'saved-original' });
  assert.equal(calls, 2);
  assert.equal(posting.pending, false);
});
test('definitive initial validation failures permit correction; server errors retain request', async () => {
  const posting = createPostingRequest();
  await assert.rejects(posting.run(async () => { throw Object.assign(new Error('Invalid'), { status: 422 }); }));
  assert.equal(posting.pending, false);
  assert.deepEqual(await posting.run(async () => 'corrected'), { value: 'corrected' });
  await assert.rejects(posting.run(async () => { throw Object.assign(new Error('Unavailable'), { status: 503 }); }));
  assert.equal(posting.pending, true);
});
test('simultaneous submissions produce only one request', async () => {
  const posting = createPostingRequest();
  let complete;
  const first = posting.run(() => new Promise(resolve => { complete = resolve; }));
  assert.equal(await posting.run(() => assert.fail('duplicate')), false);
  complete('ok');
  assert.deepEqual(await first, { value: 'ok' });
});
