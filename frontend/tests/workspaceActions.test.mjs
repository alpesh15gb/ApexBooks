import { CORE_ENHANCEMENTS } from '../src/capabilities.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import { act } from 'react';

async function workspace(role, verify, additional = [], capabilities = CORE_ENHANCEMENTS) {
  const temporary = await mkdtemp(resolve('node_modules/.workspace-tests-'));
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, MutationObserver: dom.window.MutationObserver, requestAnimationFrame: cb => setTimeout(cb, 0), ResizeObserver: class { observe() {} disconnect() {} }, IS_REACT_ACT_ENVIRONMENT: true });
  window.scrollTo = () => {};
  localStorage.token = 'synthetic-token';
  const company = { id: 'company', name: 'Synthetic company', state_code: '27', tax_mode: 'unregistered', role };
  const invoice = { id: 'invoice', kind: 'sales_invoice', name: 'Synthetic customer', number: 'INV-1', date: '2026-11-02', posted: true, amount: '100', outstanding: '40', data: { lines: [{ description: 'Service', quantity: '1', rate: '100', gst_rate: '0' }], place_of_supply: '27' } };
  const posts = [], requests = [];
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async (path, options = {}) => {
    requests.push(path);
    let data;
    if (path === '/api/capabilities') { if (capabilities === null) return { ok:false,status:404,json:async()=>({detail:'Not Found'}) }; data={api_version:'synthetic',capabilities_version:1,supported_features:capabilities}; }
    else if (path === '/api/companies') data = [company, { ...company, id: 'other-company', name: 'Other company' }];
    else if (path.includes('/records?')) data = [invoice, ...additional];
    else if (path.endsWith('/records/invoice')) { const { outstanding, ...detail } = invoice; data = detail; }
    else if (additional.some(row => path.endsWith('/records/' + row.id))) data = additional.find(row => path.endsWith('/records/' + row.id));
    else if (path.includes('/masters/') && options.method === 'PUT') data = { id: 'master-saved' };
    else if (path.endsWith('/records') && options.method === 'POST') { posts.push(JSON.parse(options.body)); data = { id: 'saved' }; }
    else if (path.endsWith('/bank-accounts')) data = [{ id: 'default', name: 'Synthetic bank' }];
    else if (path.endsWith('/preferences')) data = { document_template: 'classic' };
    else if (path.endsWith('/accounts') || path.endsWith('/journals')) data = [];
    else if (path.includes('/trial-balance')) data = { accounts: [], total_debit: '0', total_credit: '0' };
    else return { ok: false, status: 503, json: async () => ({ detail: 'Synthetic report unavailable' }) };
    return { ok: true, json: async () => data };
  };
  try {
    const outfile = resolve(temporary, 'app.mjs');
    await build({ entryPoints: ['src/main.jsx'], outfile, bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', external: ['react', 'react-dom', 'react-dom/client', 'lucide-react'], loader: { '.css': 'empty' } });
    await act(async () => { await import(pathToFileURL(outfile)); });
    const click = async text => { const button = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === text); assert.ok(button, `Button ${text}`); await act(async () => button.click()); };
    await verify({ click, posts, invoice, dom, requests });
  } finally {
    globalThis.fetch = previousFetch;
    dom.window.close();
    await rm(temporary, { recursive: true, force: true });
  }
}

test('invoice register launches allocated receipt and linked return without draft conversion', async () => {
  await workspace('owner', async ({ click, posts, invoice, dom }) => {
    await click('Sales invoices');
    assert.match(document.querySelector('.register').textContent, /Posted/);
    assert.match(document.querySelector('.register').textContent, /Part settled/);
    await click('Collect payment');
    assert.equal(document.querySelector('input[name="amount"]').value, '40');
    await act(async () => document.querySelector('.modal form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })));
    assert.equal(posts[0].kind, 'payment_in');
    assert.equal(posts[0].name, invoice.name);
    assert.deepEqual(posts[0].data.allocations, [{ document_id: invoice.id, amount: '40' }]);
    await click('Sales invoices');
    await click('Sales return');
    assert.match(document.querySelector('.modal').textContent, /Linked to INV-1/);
    await act(async () => document.querySelector('.modal form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })));
    assert.equal(posts[1].kind, 'credit_note');
    assert.equal(posts[1].data.applied_to, invoice.id);
    assert.equal(posts[1].data.source_document_id, undefined);
    assert.equal(posts[1].data.lines[0].description, 'Service');
  });
});

test('viewer can inspect ledger but cannot initiate financial mutations', async () => {
  await workspace('viewer', async ({ click }) => {
    await click('Sales invoices');
    assert.equal([...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'Collect payment'), false);
    assert.equal([...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'Sales return'), false);
    await click('Ledger');
    assert.match(document.body.textContent, /Read-only access/);
    assert.ok([...document.querySelectorAll('.ledger-form fieldset')].every(fieldset => fieldset.disabled));
  });
});

test('viewer document reference opens a read-only detail with fresh actions safely hidden', async () => {
  await workspace('viewer', async ({ click }) => {
    await click('Sales invoices');
    await click('INV-1');
    const detail = document.querySelector('.transaction-detail');
    assert.ok(detail);
    assert.match(detail.textContent, /Read-only overview/);
    assert.match(detail.textContent, /Still outstanding/);
    assert.match(detail.textContent, /₹40\.00/);
    assert.equal([...detail.querySelectorAll('button')].some(button => /Edit details|Collect payment|Sales return/.test(button.textContent)), false);
    await click('Back to register');
    assert.equal(document.querySelector('.transaction-detail'), null);
    assert.match(document.querySelector('.register').textContent, /INV-1/);
  });
});

test('cancelling a contextual receipt returns to its source register and filter', async () => {
  await workspace('owner', async ({ click, dom }) => {
    await click('Sales invoices');
    const search = document.querySelector('input[aria-label="Search this register"]');
    await act(async () => {
      Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(search, 'INV-1');
      search.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
      search.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
    });
    await click('Collect payment');
    assert.equal(document.querySelector('input[aria-label="Search this register"]').value, '');
    await click('Cancel');
    assert.match(document.querySelector('.workspace-location').textContent, /Sales invoices/);
    assert.match(document.querySelector('.register').textContent, /INV-1/);
    await click('Sales return');
    assert.equal(document.querySelector('.save-new'), null, 'Linked workflows cannot reopen stale Save & new drafts');
  });
});

test('dirty editor protects reload and browser-back dismissal asks before discarding', async () => {
  await workspace('owner', async ({ click, dom }) => {
    await click('Sales invoices');
    await click('Sales return');
    const field = document.querySelector('.modal input');
    await act(async () => field.dispatchEvent(new dom.window.Event('input', { bubbles: true })));
    const unload = new dom.window.Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unload);
    assert.equal(unload.defaultPrevented, true);
    await act(async () => window.dispatchEvent(new dom.window.PopStateEvent('popstate')));
    assert.match(document.body.textContent, /Discard unsaved changes/);
    await click('Keep editing');
    assert.ok(document.querySelector('.modal form'));
  });
});

test('foreground editor makes company navigation inert and rejects background switches', async () => {
  await workspace('owner', async ({ click, dom }) => {
    await click('Sales invoices');
    await click('Sales return');
    const dialog = document.querySelector('.modal');
    const field = dialog.querySelector('input');
    await act(async () => field.dispatchEvent(new dom.window.Event('input', { bubbles: true })));
    const company = document.querySelector('select[aria-label="Choose company"]');
    assert.ok(company.closest('[inert]'));
    company.focus();
    assert.notEqual(document.activeElement, company, 'Programmatic focus cannot escape the dialog');
    await act(async () => {
      company.value = 'other-company';
      company.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
    });
    assert.equal(company.value, 'company');
    assert.ok(document.querySelector('.modal form'), 'Dirty editor remains mounted with its retry state');
    await click('Cancel');
    await click('Discard draft');
    assert.equal(company.closest('[inert]'), null, 'Background becomes interactive after dismissal');
  });
});

test('estimate detail can create a linked nonposting sales order', async () => {
  const estimate = { id: 'estimate', kind: 'estimate', name: 'Synthetic customer', number: 'EST-1', date: '2026-11-02', amount: '100', posted: false, data: { lines: [{ description: 'Service', quantity: '1', rate: '100', gst_rate: '0' }] } };
  await workspace('owner', async ({ click, posts, dom }) => {
    await click('Estimates');
    await click('EST-1');
    assert.match(document.querySelector('.transaction-detail').textContent, /No stock, cash or revenue posted/);
    await click('Create sales order');
    assert.match(document.querySelector('.modal').textContent, /New sales order/);
    await act(async () => document.querySelector('.modal form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })));
    assert.equal(posts[0].kind, 'sales_order');
    assert.equal(posts[0].data.source_document_id, 'estimate');
  }, [estimate]);
});

test('initial company history does not duplicate the dashboard report requests', async () => {
  await workspace('owner', async ({ click, requests }) => {
    assert.equal(requests.filter(path => path.includes('/reports/summary?')).length, 1);
    const first = requests.find(path => path.includes('/records?'));
    assert.match(first, /limit=500/);
    await click('Refresh');
    assert.equal(requests.filter(path => path.includes('/reports/summary?')).length, 2);
    assert.equal(requests.filter(path => path.includes('/records?')).length, 2);
    assert.match(document.body.textContent, /temporarily unavailable/, 'Terminal report error is not an endless loading placeholder');
  });
});

test('editing a master does not leave a stale origin for the next new invoice', async () => {
 await workspace('owner', async ({ click, posts, dom }) => {
  await click('Items');
  assert.ok(document.querySelector('[aria-label="Master status"]').closest('.expanded-controls'));
  await click('Edit');
  await act(async () => document.querySelector('.modal form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })));
  await click('Sales invoices'); await click('Add sales invoice');
  await act(async () => document.querySelector('.modal form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })));
  assert.equal(posts.at(-1).kind,'sales_invoice');
  assert.match(document.querySelector('.page-heading h1')?.textContent || document.body.textContent,/Sales invoices/);
  assert.equal(window.location.hash,'#/sales_invoice');
 }, [{id:'catalog-item',kind:'item',name:'Synthetic cable',date:'2026-11-02',data:{sale_rate:'10',purchase_rate:'8'}}]);
});

test('older API disables new workflows while core invoice register remains usable', async () => {
 await workspace('owner',async ({click, requests}) => {
  const recurring=[...document.querySelectorAll('button')].find(button=>button.textContent.trim()==='Recurring drafts');
  assert.equal(recurring.disabled,true);assert.match(document.body.textContent,/newer tools are unavailable/);
  await click('Sales invoices');assert.match(document.querySelector('.register').textContent,/INV-1/);
  await click('Items');assert.equal([...document.querySelectorAll('button')].find(button=>button.textContent.includes('Low stock & reorder')).disabled,true);
  assert.equal(requests.filter(path=>path==='/api/capabilities').length,1);
 },[],null);
});
