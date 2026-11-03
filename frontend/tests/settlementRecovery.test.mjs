import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';

const temp = await mkdtemp(resolve('node_modules/.settlement-recovery-'));
const outfile = resolve(temp, 'components.mjs');
await build({ stdin: { contents: `export { default as Advances } from './src/Advances.jsx'; export { CreditSettlements } from './src/AccountingWorkflows.jsx'; export { hasPendingPostings } from './src/postingRegistry.js';`, resolveDir: process.cwd(), loader: 'jsx' }, outfile, bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', external: ['react', 'react-dom', 'lucide-react'] });
const { Advances, CreditSettlements, hasPendingPostings } = await import(pathToFileURL(outfile));
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import('react-dom/client');

for (const [name, Component, sourceKind, balance] of [
  ['advance', Advances, 'payment_in', 'advance_remaining'],
  ['credit', CreditSettlements, 'credit_note', 'credit_remaining'],
]) for (const action of ['apply', 'refund']) for (const removeSource of [false, true]) {
  test(`${name} ${action} uncertain save recovers after ${removeSource ? "source removal" : "source rename and zero balance"}`, async () => {
    const root = createRoot(document.getElementById('root'));
    const source = { id: 'source', kind: sourceKind, name: 'Synthetic customer', amount: '100', date: '2026-11-03', [balance]: '100', data: {} };
    const target = { id: 'invoice', kind: 'sales_invoice', posted: true, name: source.name, amount: '100', outstanding: '100', data: {} };
    const requests = [];
    let confirm;
    const api = async (path, options) => {
      if (path.endsWith('/bank-accounts')) return [];
      requests.push({ path, options });
      if (requests.length === 1) throw Object.assign(new Error('Response lost after commit'), { status: 0 });
      if (requests.length === 2) return {}; // A successful HTTP response without a verifiable posting.
      const body = JSON.parse(options.body);
      return new Promise(resolve => { confirm = () => resolve({
        id: 'confirmed-original', posted: true, date: body.date, amount: '100.00',
        kind: name === 'advance' ? action === 'apply' ? 'advance_application' : 'advance_refund' : action === 'apply' ? 'credit_application' : 'customer_refund',
        data: {
          [name === 'advance' ? 'advance_id' : 'credit_note_id']: source.id,
          ...(name === 'advance' || action === 'apply' ? { payment_kind: 'payment_in' } : {}),
          ...(action === 'apply' ? { applied_to: target.id } : { payment_account: 'cash', bank_account_id: 'default' }),
        },
      }); });
    };
    const props = { companyId: 'synthetic-company', kind: 'payment_in', api, canWrite: true, refresh: async () => {} };
    try {
      await act(async () => root.render(React.createElement(Component, { ...props, records: [source, target] })));
      await act(async () => { const select = document.querySelector('select'); select.value = source.id; select.dispatchEvent(new window.Event('change', { bubbles: true })); });
      const selectValue = async (select, value) => act(async () => {
        select.value = value; select.dispatchEvent(new window.Event('change', { bubbles: true }));
      });
      const actionSelect = [...document.querySelectorAll('select')].find(select => [...select.options].some(option => option.value === 'refund'));
      await selectValue(actionSelect, action);
      if (action === 'apply') {
        const targetSelect = [...document.querySelectorAll('select')].find(select => [...select.options].some(option => option.value === target.id));
        await selectValue(targetSelect, target.id);
      }
      await act(async () => {
        const amount = document.querySelector('input[type="number"]');
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(amount, '100');
        amount.dispatchEvent(new window.Event('input', { bubbles: true }));
        amount.dispatchEvent(new window.Event('change', { bubbles: true }));
      });
      await act(async () => document.querySelector('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
      assert.equal(JSON.parse(requests[0].options.body).amount, '100');
      if (action === 'apply') assert.equal(JSON.parse(requests[0].options.body).data.applied_to, target.id);
      assert.equal(hasPendingPostings(), true);
      // A user clicks the global Refresh after the server committed but its response was lost.
      await act(async () => root.render(React.createElement(Component, { ...props, records: removeSource ? [] : [{ ...source, name: 'Renamed after posting', [balance]: '0' }, { ...target, outstanding: '0' }] })));
      assert.equal(hasPendingPostings(), true);
      const retry = [...document.querySelectorAll('button')].find(button => button.textContent.trim() === 'Retry previous save' && !button.disabled);
      assert.ok(retry, 'pending save must retain a usable retry control after balances refresh');
      await act(async () => { retry.click(); retry.click(); });
      assert.equal(requests.length, 2, "concurrent recovery clicks must not repeat POST");
      assert.equal(hasPendingPostings(), true, 'a malformed retry response cannot release the pending operation');
      const retryAgain = [...document.querySelectorAll('button')].find(button => button.textContent.trim() === 'Retry previous save' && !button.disabled);
      assert.ok(retryAgain);
      await act(async () => { retryAgain.click(); retryAgain.click(); });
      assert.equal(requests.length, 3);
      await act(async () => confirm());
      assert.deepEqual(requests[0], requests[1]);
      assert.deepEqual(requests[0], requests[2]);
      assert.equal(hasPendingPostings(), false);
    } finally { await act(async () => root.unmount()); }
  });
}
test.after(async () => { dom.window.close(); await rm(temp, { recursive: true, force: true }); });
