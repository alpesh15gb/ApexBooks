import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import { act } from 'react';

for (const flow of ['pos', 'payment', 'refresh401', 'pos-body', 'payment-body', 'refresh401-body', 'transfer', 'transfer401', 'transfer-body']) test(`${flow}: late in-flight response must not change the replacement session`, async t => {
  const payment = flow.startsWith('payment'), transfer = flow.startsWith('transfer'), refresh401 = flow.startsWith('refresh401'), bodyOnly = flow.endsWith('body');
  const temporary = await mkdtemp(resolve('node_modules/.inflight-session-'));
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage,
    MutationObserver: dom.window.MutationObserver, requestAnimationFrame: cb => setTimeout(cb, 0), ResizeObserver: class { observe() {} disconnect() {} }, IS_REACT_ACT_ENVIRONMENT: true });
  window.scrollTo = () => {};
  localStorage.token = 'original-synthetic-session';
  const company = { id: 'c1', name: 'Synthetic company', state_code: '27', tax_mode: 'unregistered', role: 'owner' };
  const invoice = { id: 'invoice', kind: 'sales_invoice', name: 'Synthetic customer', number: 'INV-1', date: '2026-11-03', posted: true, amount: '100', outstanding: '40', data: { lines: [{ description: 'Service', quantity: '1', rate: '100', gst_rate: '0' }] } };
  const item = { id: 'item', kind: 'item', name: 'Synthetic item', date: '2026-11-03', data: { sale_rate: '100', gst_rate: '0' } };
  const requests = [];
  const previousFetch = globalThis.fetch;
  let finishPost, finishRefresh, deferRefresh = false, roleDenied = false, postCount = 0;
  const savedRecord = () => ({ id: 'old-post', kind: payment ? 'payment_in' : transfer ? 'bank_transfer' : 'pos', posted: true, number: 'OLD-SESSION-RECEIPT', amount: payment ? '40' : '100' });
  const denied = () => ({ ok: false, status: 403, json: async () => ({ detail: 'Write access required' }) });
  const response = data => ({ ok: true, json: async () => data });
  globalThis.fetch = async (path, options = {}) => {
    requests.push({ path, options });
    if (path === '/api/companies') return response([company, { ...company, id: 'c2', name: 'Other company' }]);
    if (path.includes('/records?')) {
      if (deferRefresh) {
        deferRefresh = false;
        if (bodyOnly) return { ok: false, status: 401, json: () => new Promise(resolve => { finishRefresh = () => resolve({ detail: 'Original session expired' }); }) };
        return new Promise(resolve => { finishRefresh = () => resolve({ ok: false, status: 401, json: async () => ({ detail: 'Original session expired' }) }); });
      }
      return response([invoice, item]);
    }
    if (path.endsWith('/records/invoice')) return response(invoice);
    if (path.endsWith('/documents/preview')) return response({ amount: '100', data: { cgst: '0', sgst: '0', igst: '0' } });
    if (path.endsWith('/records') && options.method === 'POST') {
      postCount++;
      if (postCount > 1) return roleDenied ? denied() : response(savedRecord());
      if (bodyOnly) return { ok: true, json: () => new Promise(resolve => { finishPost = () => resolve(savedRecord()); }) };
      return new Promise(resolve => { finishPost = () => resolve(flow === 'transfer401' ? { ok: false, status: 401, json: async () => ({ detail: 'Original session expired' }) } : response(savedRecord())); });
    }
    if (path.endsWith('/preferences')) return response({ document_template: 'classic' });
    if (path.endsWith('/bank-accounts')) return response([{ id: 'default', name: 'Synthetic bank' }]);
    if (path.endsWith('/accounts') || path.endsWith('/journals')) return response([]);
    return { ok: false, status: 503, json: async () => ({ detail: 'Synthetic report unavailable' }) };
  };
  const click = async text => {
    const button = [...document.querySelectorAll('button')].find(button => button.textContent.trim() === text);
    assert.ok(button, text); await act(async () => button.click());
  };
  try {
    const outfile = resolve(temporary, 'app.mjs');
    await build({ entryPoints: ['src/main.jsx'], outfile, bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', external: ['react', 'react-dom', 'react-dom/client', 'lucide-react'], loader: { '.css': 'empty' } });
    await act(async () => { await import(pathToFileURL(outfile)); });
    // Begin this read before posting; pending financial commands now defer new refreshes.
    if (refresh401) { deferRefresh = true; await click('Refresh'); assert.equal(typeof finishRefresh, 'function'); }
    if (payment) {
      await click('Sales invoices'); await click('Collect payment');
      assert.equal(document.querySelector('input[name="amount"]').value, '40');
      await act(async () => document.querySelector('.modal form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
    } else if (transfer) {
      await click('Cash & bank'); await click('Record cash/bank transfer');
      await act(async () => {
        const amount = document.querySelector('.modal input[type="number"]');
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(amount, '100');
        amount.dispatchEvent(new window.Event('input', { bubbles: true }));
      });
      await act(async () => document.querySelector('.modal form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
      assert.equal(JSON.parse(requests.find(({options}) => options.method === 'POST' && options.headers['Idempotency-Key']).options.body).amount, '100');
    } else {
      await click('POS'); await act(async () => document.querySelector('.pos-product').click());
      await act(async () => new Promise(resolve => setTimeout(resolve, 250)));
      await click('Complete sale');
    }
    assert.equal(typeof finishPost, 'function');
    const companyPicker = document.querySelector('[aria-label="Choose company"]');
    await act(async () => { companyPicker.value = 'c2'; companyPicker.dispatchEvent(new window.Event('change', { bubbles: true })); });
    assert.equal(companyPicker.value, 'c1', 'normal company navigation is already blocked');
    if (refresh401) {
      assert.equal(typeof finishRefresh, 'function');
    }
    localStorage.token = 'replacement-synthetic-session';
    await act(async () => window.dispatchEvent(new window.StorageEvent('storage', { key: 'token', oldValue: 'original-synthetic-session', newValue: 'replacement-synthetic-session', storageArea: localStorage })));
    if (refresh401) {
      await act(async () => finishRefresh());
      const retainedReplacement = localStorage.token === 'replacement-synthetic-session';
      await act(async () => finishPost());
      t.diagnostic(JSON.stringify({ retainedReplacement, authScreen: !!document.querySelector('.auth-page') }));
      assert.equal(retainedReplacement, true, 'old refresh 401 must not remove the replacement token');
    } else {
      await act(async () => finishPost());
      const newSessionRefreshes = requests.filter(({ path, options }) => path.includes('/records?') && options.headers.Authorization === 'Bearer replacement-synthetic-session');
      const evidence = { newSessionRefreshes: newSessionRefreshes.length, staleReceiptShown: !!document.querySelector('.pos-receipt'), cartRows: document.querySelectorAll('.pos-grid .line-card').length, paymentEditorClosed: !document.querySelector('.modal form') };
      t.diagnostic(JSON.stringify(evidence));
      assert.equal(newSessionRefreshes.length, 0, 'late old-session acknowledgement must not refresh records under new token');
      if (!payment && !transfer) { assert.equal(evidence.staleReceiptShown, false); assert.equal(evidence.cartRows, 1); }
      else assert.equal(evidence.paymentEditorClosed, false);
    }
    const pendingUnload = new window.Event('beforeunload', { cancelable: true });
    window.dispatchEvent(pendingUnload); assert.equal(pendingUnload.defaultPrevented, true, 'late response cannot release uncertain original command');
    const retry = async () => {
      if (payment || transfer) await act(async () => document.querySelector('.modal form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
      else await click('Complete sale');
    };
    await retry(); assert.equal(postCount, 1, 'replacement session must not replay original command');
    localStorage.token = 'original-synthetic-session';
    roleDenied = true;
    await retry(); assert.equal(postCount, 2);
    const deniedUnload = new window.Event('beforeunload', { cancelable: true });
    window.dispatchEvent(deniedUnload); assert.equal(deniedUnload.defaultPrevented, true, 'server role rejection cannot erase uncertain command');
    roleDenied = false;
    await retry(); assert.equal(postCount, 3);
    const posts = requests.filter(({ path, options }) => path.endsWith('/records') && options.method === 'POST');
    for (const posted of posts) assert.deepEqual(posted, posts[0], 'original company, actor, body and key must survive recovery');
    const recoveredUnload = new window.Event('beforeunload', { cancelable: true });
    window.dispatchEvent(recoveredUnload); assert.equal(recoveredUnload.defaultPrevented, false);
    if (payment || transfer) assert.equal(document.querySelector('.modal form'), null);
    else assert.match(document.querySelector('.pos-receipt').textContent, /OLD-SESSION-RECEIPT/);
  } finally { globalThis.fetch = previousFetch; dom.window.close(); await rm(temporary, { recursive: true, force: true }); }
});
