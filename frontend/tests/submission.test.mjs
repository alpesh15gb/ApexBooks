import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';

const temporary = await mkdtemp(resolve('node_modules/.submission-tests-'));
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const company = { id: 'synthetic-company', name: 'Synthetic', tax_mode: 'unregistered', state_code: '27', role: 'owner' };
async function component(name) {
  const outfile = resolve(temporary, `${name}.mjs`);
  await build({ entryPoints: [`src/${name}.jsx`], outfile, bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', external: ['react', 'react-dom', 'lucide-react'] });
  return (await import(pathToFileURL(outfile))).default;
}
const RecordEditor = await component('RecordEditor');
const PosWorkspace = await component('PosWorkspace');
const StockAdjustment = await component('StockAdjustment');
const Advances = await component('Advances');
const CashTransfer = await component('CashTransfer');
globalThis.localStorage = dom.window.localStorage;
const api = async path => path.endsWith('bank-accounts') ? [] : { amount: '100', data: { cgst: 0, sgst: 0, igst: 0 } };
const submit = form => form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }));

test('document submission locks draft fields and rejects synchronous double submits', async () => {
  const root = createRoot(document.getElementById('root'));
  let calls = 0, finish;
  const save = () => { calls++; return new Promise(resolve => { finish = resolve; }); };
  await act(async () => root.render(React.createElement(RecordEditor, {
    kind: 'payment_in', company, companyId: company.id, records: [], save, api,
    Modal: ({ children }) => React.createElement('div', null, children),
    labels: { payment_in: 'Payments in' }, documentKinds: [], money: String,
    today: () => '2026-11-02', close: () => {},
  })));
  await act(async () => { submit(document.querySelector('form')); submit(document.querySelector('form')); });
  assert.equal(calls, 1);
  assert.equal(document.querySelector('fieldset').disabled, true);
  await act(async () => finish());
  assert.equal(document.querySelector('fieldset').disabled, false);
  await act(async () => root.unmount());
});

test('POS freezes the cart during posting and clears it only after confirmation', async () => {
  const root = createRoot(document.getElementById('root'));
  let calls = 0, finish;
  const posApi = (path, options) => path.endsWith('/records')
    ? (calls++, new Promise(resolve => { finish = resolve; })) : api(path, options);
  await act(async () => root.render(React.createElement(PosWorkspace, {
    company, records: [{ id: 'item-a', kind: 'item', name: 'Synthetic item', data: { sale_rate: '100' } }],
    api: posApi, refresh: async () => {}, onPdf: () => {},
  })));
  await act(async () => document.querySelector('.pos-product').click());
  await act(async () => new Promise(resolve => setTimeout(resolve, 250)));
  await act(async () => { submit(document.querySelector('form')); submit(document.querySelector('form')); });
  assert.equal(calls, 1);
  assert.equal(document.querySelector('fieldset').disabled, true);
  assert.equal(document.querySelector('input[aria-label="Search POS items or scan barcode"]').disabled, true);
  assert.equal(document.querySelectorAll('.line-card').length, 1);
  await act(async () => finish({ number: 'POS-1', amount: '100' }));
  assert.equal(document.querySelectorAll('.line-card').length, 0);
  assert.match(document.querySelector('.pos-receipt').textContent, /Sale completed/);
  await act(async () => root.unmount());
});
test('POS uncertain response retries unchanged request and renders recovered receipt', async () => {
  const root = createRoot(document.getElementById('root'));
  const requests = [];
  const posApi = async (path, options) => {
    if (!path.endsWith('/records')) return api(path, options);
    requests.push(options);
    if (requests.length === 1) throw new TypeError('Connection lost');
    return { number: 'RECOVERED-1', amount: '100' };
  };
  await act(async () => root.render(React.createElement(PosWorkspace, {
    company, records: [{ id: 'item-a', kind: 'item', name: 'Synthetic item', data: { sale_rate: '100' } }],
    api: posApi, refresh: async () => {}, onPdf: () => {},
  })));
  await act(async () => document.querySelector('.pos-product').click());
  await act(async () => new Promise(resolve => setTimeout(resolve, 250)));
  await act(async () => submit(document.querySelector('form')));
  assert.equal(document.querySelector('fieldset').disabled, true);
  assert.match(document.body.textContent, /previous response was not confirmed/);
  assert.equal(document.querySelector('button.button.primary').disabled, false);
  await act(async () => submit(document.querySelector('form')));
  assert.deepEqual(requests[0], requests[1]);
  assert.match(document.querySelector('.pos-receipt').textContent, /RECOVERED-1/);
  await act(async () => root.unmount());
});

test('stock adjustment retains draft key on retry and cannot be dismissed while uncertain', async () => {
  const root = createRoot(document.getElementById('root'));
  const requests = []; let closed = false;
  const save = async (body, key) => {
    requests.push({ body, key });
    if (requests.length === 1) throw new TypeError('Connection lost');
  };
  await act(async () => root.render(React.createElement(StockAdjustment, {
    items: [{ id: 'item-a', name: 'Synthetic stock', data: { unit: 'pcs' } }],
    save, close: () => { closed = true; },
  })));
  await act(async () => submit(document.querySelector('form')));
  assert.equal(document.querySelector('fieldset').disabled, true);
  await act(async () => document.querySelector('button[aria-label="Close"]').click());
  assert.equal(closed, false);
  await act(async () => submit(document.querySelector('form')));
  assert.deepEqual(requests[0], requests[1]);
  assert.ok(requests[0].key);
  assert.equal(document.querySelector('fieldset').disabled, false);
  await act(async () => root.unmount());
});
test('advance application locks selection and retries the same key after uncertain response', async () => {
  const root = createRoot(document.getElementById('root'));
  const requests = [];
  const advanceApi = async (path, options) => {
    if (path.endsWith('bank-accounts')) return [];
    requests.push({ path, options });
    if (requests.length === 1) throw new TypeError('Connection lost');
    const body = JSON.parse(options.body);
    return { id: 'application', posted: true, kind: 'advance_application', date: body.date, amount: body.amount, data: { advance_id: 'advance', applied_to: body.data.applied_to, payment_kind: 'payment_in' } };
  };
  await act(async () => root.render(React.createElement(Advances, {
    companyId: company.id, kind: 'payment_in', canWrite: true, refresh: async () => {}, api: advanceApi,
    records: [
      { id: 'advance', kind: 'payment_in', advance_remaining: '100', name: 'Synthetic customer', amount: '100' },
      { id: 'invoice', kind: 'sales_invoice', posted: true, outstanding: '100', name: 'Synthetic customer' },
    ],
  })));
  await act(async () => { const select = document.querySelector('select'); select.value = 'advance'; select.dispatchEvent(new dom.window.Event('change', { bubbles: true })); });
  await act(async () => {
    const target = [...document.querySelectorAll('select')].find(select => [...select.options].some(option => option.value === 'invoice'));
    target.value = 'invoice'; target.dispatchEvent(new window.Event('change', { bubbles: true }));
    const amount = document.querySelector('input[type="number"]');
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(amount, '100');
    amount.dispatchEvent(new window.Event('input', { bubbles: true }));
  });
  await act(async () => submit(document.querySelector('form')));
  assert.equal(document.querySelector('select').disabled, true);
  assert.equal(document.querySelector('fieldset').disabled, true);
  await act(async () => submit(document.querySelector('form')));
  assert.deepEqual(requests[0], requests[1]);
  assert.equal(document.querySelector('fieldset').disabled, false);
  await act(async () => root.unmount());
});

test('cash transfer retains its key through an interrupted response and blocks dismissal', async () => {
  const root = createRoot(document.getElementById('root'));
  const previousFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (path, options) => {
    requests.push({ path, options });
    if (requests.length === 1) throw new TypeError('Connection lost');
    return { ok: true, json: async () => ({ id: 'transfer' }) };
  };
  try {
    await act(async () => root.render(React.createElement(CashTransfer, {
      companyId: company.id, role: 'owner', onSaved: () => {}, banks: [{ id: 'default', name: 'Synthetic bank' }],
    })));
    await act(async () => document.querySelector('.cash-transfer-button').click());
    await act(async () => submit(document.querySelector('form')));
    assert.equal(document.querySelector('fieldset').disabled, true);
    assert.equal(document.querySelector('button[aria-label="Close"]').disabled, true);
    await act(async () => submit(document.querySelector('form')));
    assert.deepEqual(requests[0], requests[1]);
    assert.equal(document.querySelector('form'), null);
  } finally {
    globalThis.fetch = previousFetch;
    await act(async () => root.unmount());
  }
});

test.after(async () => { dom.window.close(); await rm(temporary, { recursive: true, force: true }); });
