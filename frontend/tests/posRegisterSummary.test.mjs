import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { after, test } from 'node:test';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { businessDate } from '../src/businessDate.js';
import { formatRegisterMoney, parseRegisterMoney, posCloseCsv, reconcilePosCash, summarizePosDay } from '../src/posRegisterSummary.js';

const date = '2026-11-15';
const yesterday = '2026-11-14';
const row = (id, kind, amount, data = {}, when = date, status = {}) => ({
  id, number: id, kind, amount, data, date: when, posted: true, ...status,
});
const records = [
  row('POS-1', 'pos', '12.35', { tender_amount: '20.00', change_amount: '7.65' }),
  row('POS-2', 'pos', '15.75', { payment_account: 'bank' }),
  row('POS-3', 'pos', '21.20', { payment_account: 'split', cash_amount: '8.20', bank_amount: '13.00' }),
  row('POS-4', 'pos', '500.00', {}, date, { posted: false, cancelled: true }),
  row('POS-5', 'pos', '250.00', {}, yesterday),
  row('CN-1', 'credit_note', '7.50', { applied_to: 'POS-5' }, yesterday),
  row('RF-1', 'customer_refund', '2.10', { credit_note_id: 'CN-1', payment_account: 'cash' }),
  row('RF-2', 'customer_refund', '5.40', { credit_note_id: 'CN-1', payment_account: 'bank' }),
  row('RF-3', 'customer_refund', '50.00', { credit_note_id: 'CN-1' }, date, { posted: false, cancelled: true }),
  row('INV-1', 'sales_invoice', '800.00'),
  row('CN-2', 'credit_note', '100.00', { applied_to: 'INV-1' }),
  row('RF-4', 'customer_refund', '100.00', { credit_note_id: 'CN-2' }),
  row('CN-3', 'credit_note', '10.00', { applied_to: 'POS-5' }),
];

test('day totals count retained sales and later linked refunds against the original POS source', () => {
  const day = summarizePosDay(records, date);
  assert.equal(day.saleCount, 3);
  assert.equal(day.refundCount, 2);
  assert.equal(day.cancelledCount, 1);
  assert.equal(day.unresolvedCount, 0);
  assert.equal(day.cashSales, 2055n);
  assert.equal(day.bankSales, 2875n);
  assert.equal(day.cashRefunds, 210n);
  assert.equal(day.bankRefunds, 540n);
  assert.equal(day.rows.at(-1).receipt, 'POS-5');
});

test('cash variance includes the float and other cash movement with exact paise', () => {
  const day = summarizePosDay(records, date);
  const entries = { openingFloat: '250.50', cashIn: '10.00', cashOut: '5.05', cashCounted: '272.80' };
  const result = reconcilePosCash(day, entries);
  assert.equal(result.expected, 27390n);
  assert.equal(result.variance, -110n);
  assert.deepEqual(result.invalidFields, []);
  assert.equal(reconcilePosCash(day, {}).variance, null);
  const bad = reconcilePosCash(day, { ...entries, cashOut: '1.234' });
  assert.equal(bad.expected, null);
  assert.deepEqual(bad.invalidFields, ['cashOut']);
  assert.equal(formatRegisterMoney(parseRegisterMoney('9999999999999.99')), '₹99,99,99,99,99,999.99');
});

test('an unresolved split tender blocks reconciled totals and export', () => {
  const day = summarizePosDay([
    ...records, row('POS-6', 'pos', '10.00', { payment_account: 'split', cash_amount: '2.00', bank_amount: '2.00' }),
  ], date);
  const reconciliation = reconcilePosCash(day, { openingFloat: '50', cashCounted: '68.45' });
  assert.equal(day.unresolvedCount, 1);
  assert.equal(reconciliation.expected, null);
  assert.throws(() => posCloseCsv({ companyName: 'Shop', date, day, reconciliation }), /valid drawer counts/);
});

test('CSV preserves decimal amounts and protects user-controlled text from spreadsheet formulas', () => {
  const day = summarizePosDay([
    row('@HYPERLINK("url","name")', 'pos', '10.00'),
  ], date);
  const result = reconcilePosCash(day, { openingFloat: '100.00', cashCounted: '109.00' });
  const csv = posCloseCsv({ companyName: ' =SUM(10,20)', date, day, reconciliation: result });
  assert.ok(csv.startsWith('\ufeff'));
  assert.match(csv, /Company,"' =SUM\(10,20\)"/);
  assert.match(csv, /Cash over \/ short,-1\.00/);
  assert.match(csv, /Sale,"'@HYPERLINK\(""url"",""name""\)","'@HYPERLINK\(""url"",""name""\)",10\.00,0\.00/);
});

const temporary = await mkdtemp(resolve('node_modules/.pos-summary-test-'));
const entry = resolve(temporary, 'PosRegisterSummary.mjs');
await build({
  entryPoints: ['src/PosRegisterSummary.jsx'],
  outfile: entry,
  bundle: true,
  platform: 'node',
  format: 'esm',
  jsx: 'automatic',
  external: ['react', 'react-dom', 'lucide-react'],
  loader: { '.css': 'empty' },
});
const PosRegisterSummary = (await import(pathToFileURL(entry))).default;
after(() => rm(temporary, { recursive: true, force: true }));

test('cashier can check a count and export only after the posted totals are refreshed', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true });
  const { createRoot } = await import('react-dom/client');
  const reactRoot = createRoot(document.getElementById('root'));
  const originalCreateUrl = URL.createObjectURL;
  const downloads = [];
  URL.createObjectURL = file => { downloads.push(file); return 'blob:pos-test'; };
  dom.window.HTMLAnchorElement.prototype.click = () => {};
  try {
    const today = businessDate();
    const first = [row('POS-A', 'pos', 10, {}, today)];
    const latest = [...first, row('POS-B', 'pos', 5, {}, today)];
    let refreshCount = 0;
    function Harness() {
      const [rows, setRows] = React.useState(first);
      return React.createElement(PosRegisterSummary, {
        companyName: 'Example shop', records: rows, refresh: async () => {
          refreshCount++;
          setRows(latest);
          return latest;
        },
      });
    }
    await act(async () => reactRoot.render(React.createElement(Harness)));
    const exportButton = [...document.querySelectorAll('button')].find(button => button.textContent.includes('Export count CSV'));
    assert.equal(exportButton.disabled, true);
    const fields = [...document.querySelectorAll('fieldset input')];
    for (const [input, value] of [[fields[0], '50.00'], [fields[3], '60.00']]) {
      Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(input, value);
      await act(async () => input.dispatchEvent(new dom.window.Event('input', { bubbles: true })));
      await act(async () => input.dispatchEvent(new dom.window.Event('change', { bubbles: true })));
    }
    assert.equal(exportButton.disabled, false);
    assert.match(document.querySelector('.pos-reconciliation-results').textContent, /Expected cash₹60\.00Cash variance₹0\.00/);
    await act(async () => exportButton.click());
    assert.equal(refreshCount, 1);
    assert.equal(downloads.length, 0);
    assert.match(document.querySelector('[role="alert"]').textContent, /Sales or refunds changed/);
    assert.match(document.querySelector('.pos-reconciliation-results').textContent, /Expected cash₹65\.00Cash short₹5\.00/);
    await act(async () => exportButton.click());
    assert.equal(refreshCount, 2);
    assert.equal(downloads.length, 1);
    assert.match(await downloads[0].text(), /Cash over \/ short,-5\.00/);
  } finally {
    URL.createObjectURL = originalCreateUrl;
    await act(async () => reactRoot.unmount());
    dom.window.close();
  }
});

test('register open recovery reuses the request key, then close saves the counted variance', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true });
  const { createRoot } = await import('react-dom/client');
  const reactRoot = createRoot(document.getElementById('root'));
  const totals = {
    cash_sales: '10.00', bank_sales: '0.00', cash_refunds: '0.00', bank_refunds: '0.00',
    cash_in: '0.00', cash_out: '0.00', expected_cash: '110.00',
    sales_count: 1, refund_count: 0, movement_count: 0,
  };
  const time = '2026-11-15T05:01:22+00:00';
  const drawer = {
    id: 'register-1', data: { created_at: time, opened_by: 'cashier@example.test', opening_float: '100.00' },
    totals, movements: [], snapshot: 'abc',
  };
  let state = { active: null, closed: [] };
  const calls = [];
  const api = async (path, options) => {
    if (options.method !== 'POST') return state;
    calls.push({ path, key: options.headers['Idempotency-Key'], body: JSON.parse(options.body) });
    if (path.endsWith('/open')) {
      state = { active: drawer, closed: [] };
      if (calls.length === 1) throw Object.assign(new Error('Connection interrupted'), { status: 503 });
      return drawer;
    }
    const closed = {
      ...drawer, data: {
        ...drawer.data, closed_at: time, counted_cash: '109.00', variance: '-1.00',
        closed_by: 'cashier@example.test', closed_totals: totals, close_reason: 'Recount confirmed shortage',
      },
    };
    state = { active: null, closed: [closed] };
    return closed;
  };
  async function input(selector, value) {
    const field = document.querySelector(selector);
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(field, value);
    await act(async () => field.dispatchEvent(new dom.window.Event('input', { bubbles: true })));
  }
  const button = text => [...document.querySelectorAll('button')].find(button => button.textContent.trim() === text);

  try {
    await act(async () => reactRoot.render(React.createElement(PosRegisterSummary, {
      companyId: 'company-1', api, canWrite: true, registerEnabled: true, records: [], companyName: 'Store',
    })));
    await input('.pos-register-fields input', '100.00');
    await act(async () => button('Open register').click());
    assert.match(document.querySelector('.pos-reconciliation [role="alert"]').textContent, /Connection interrupted/);
    await act(async () => button('Retry open register').click());
    assert.deepEqual(calls[0], calls[1]);
    assert.equal(document.querySelector('.pos-register-status').textContent, 'Open');

    const closeFields = 'section[aria-label="POS register session"] form:last-of-type .pos-register-fields';
    await input(closeFields + ' label:first-of-type input', '109.00');
    assert.equal(button('Close register').disabled, true);
    await input(closeFields + ' label:nth-of-type(2) input', 'Recount confirmed shortage');
    assert.equal(button('Close register').disabled, false);
    await act(async () => button('Close register').click());
    assert.deepEqual(calls[2].body, {
      counted_cash: '109.00', reason: 'Recount confirmed shortage', snapshot: 'abc',
    });
    assert.equal(document.querySelector('.pos-register-status').textContent, 'Closed');
    assert.match(document.querySelector('.pos-register-closed summary').textContent, /Counted ₹109\.00 · Variance -₹1\.00/);
  } finally {
    await act(async () => reactRoot.unmount());
    dom.window.close();
  }
});
