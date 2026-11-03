import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { inlineItemCreator } from '../src/inlineItem.js';
import { createRequestScope } from '../src/requestScope.js';
const temp = await mkdtemp(resolve('node_modules/.inline-item-tests-'));
await build({ entryPoints: ['src/RecordEditor.jsx'], outfile: resolve(temp, 'editor.mjs'), bundle: true, platform: 'node', format: 'esm', external: ['react', 'react-dom', 'lucide-react'] });
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import('react-dom/client');
const Editor = (await import(pathToFileURL(resolve(temp, 'editor.mjs')))).default;
after(async () => { dom.window.close(); await rm(temp, { recursive: true, force: true }); });
const Modal = ({ children, close }) => React.createElement('section', { onKeyDown: e => { if (e.key === 'Escape') close(); } }, children);
const line = { description: 'Draft service', quantity: '2', rate: '125', gst_rate: '0', tax_treatment: 'nil_rated' };
const company = { role: 'owner', tax_mode: 'regular', state_code: '27', name: 'Synthetic Books' };
const item = { id: 'item-new', kind: 'item', name: 'New service', data: { item_type: 'services', sale_rate: '250', gst_rate: '18', tax_treatment: 'taxable', unit: 'hour', hsn: '9983' } };
const button = text => [...document.querySelectorAll('button')].find(el => el.textContent === text);
const child = () => document.querySelector('.inline-party-form');
async function click(text) { await act(async () => button(text).click()); }
async function change(selector, value) {
  await act(async () => { const el = document.querySelector(selector); const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : el.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value); el.dispatchEvent(new window.Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true })); });
}
const submitChild = () => act(async () => child().querySelector('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
async function mount(extra = {}) {
  const root = createRoot(document.getElementById('root')); let saved, closed = 0;
  await act(async () => root.render(React.createElement(Editor, {
    kind: 'sales_invoice', company, companyId: 'c1', records: [], features: ['party_shipping_address'],
    draftSeed: { name: 'New buyer', data: { lines: [line], shipping_address: 'Manual delivery', due_date: '2026-12-01', notes: 'Keep my notes' } },
    api: async path => path.endsWith('bank-accounts') ? [] : { amount: '250', data: { lines: [] } },
    Modal, labels: { sales_invoice: 'Sales invoices' }, documentKinds: ['sales_invoice'], money: String, today: () => '2026-11-03',
    createItem: async () => item, save: payload => { saved = payload; }, close: () => { closed++; }, ...extra,
  })));
  return { root, get saved() { return saved; }, get closed() { return closed; } };
}
const invoiceForm = () => document.querySelector('form.document-form');
const submitInvoice = () => act(async () => invoiceForm().dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));

test('cancel keeps the same invoice mounted, restores focus and preserves draft fields', async () => {
  const view = await mount(); const original = invoiceForm();
  await change('details.document-notes textarea', 'Keep my edited notes');
  await click('Create item/service and add line'); assert.equal(document.activeElement.name, 'name');
  assert.equal(invoiceForm(), original); assert.equal(original.parentElement.hidden, true);
  await change('.inline-party-form [name=name]', 'Do not save');
  await act(async () => child().dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
  await act(async () => new Promise(resolve => setTimeout(resolve, 5)));
  assert.equal(child(), null); assert.equal(document.activeElement, button('Create item/service and add line'));
  await submitInvoice(); assert.equal(view.saved.name, 'New buyer'); assert.equal(view.saved.data.lines[0].rate, '125');
  assert.equal(view.saved.data.shipping_address, 'Manual delivery'); assert.equal(view.saved.data.due_date, '2026-12-01'); assert.equal(view.saved.data.notes, 'Keep my edited notes');
  await act(async () => view.root.unmount());
});
test('create uses returned identity without posting invoice or overwriting manual delivery, lines or due date', async () => {
  let calls = 0; const view = await mount({ createItem: async body => { calls++; return item; } });
  const original = invoiceForm(); await click('Create item/service and add line'); await submitInvoice(); assert.equal(view.saved, undefined);
  await change('.inline-party-form [name=name]', 'New service'); await submitChild(); assert.equal(calls, 1); assert.equal(child(), null); assert.equal(invoiceForm(), original); assert.equal(view.saved, undefined);
  assert.ok(document.querySelector('datalist#apex-item-options option[value="New service"]'));
  await submitInvoice(); assert.equal(view.saved.name, 'New buyer');
  assert.equal(view.saved.data.shipping_address, 'Manual delivery'); assert.equal(view.saved.data.due_date, '2026-12-01');
  assert.equal(view.saved.data.lines[0].quantity, '2'); assert.equal(view.saved.data.lines[0].rate, '125');
  assert.equal(view.saved.data.lines.length, 2); assert.equal(view.saved.data.lines[1].item_id, item.id);
  assert.equal(view.saved.data.lines[1].rate, '250'); assert.equal(view.saved.data.lines[1].gst_rate, '18');
  assert.equal(view.saved.data.lines[1].hsn, '9983'); assert.equal(view.saved.data.lines[1].unit, 'hour');
  await act(async () => view.root.unmount());
});
test('uncertain item save freezes details, blocks dismiss and invoice submit, and retries exact body/key only once', async () => {
  const calls = []; let rejectFirst; let date = "2026-11-03";
  const view = await mount({ today: () => date, createItem: (body, key) => { calls.push({ body, key }); return calls.length === 1 ? new Promise((_, reject) => { rejectFirst = reject; }) : Promise.resolve(item); } });
  await click('Create item/service and add line');
  await act(async () => { const form = child().querySelector('form'); form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })); window.dispatchEvent(new window.Event('apex-close-editor')); assert.ok(child()); form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })); });
  assert.equal(calls.length, 1);
  await act(async () => rejectFirst(new Error('Connection interrupted')));
  assert.equal(child().querySelector('fieldset').disabled, true); assert.match(child().textContent, /response was not confirmed/);
  await act(async () => window.dispatchEvent(new window.Event('apex-close-editor'))); assert.ok(child()); assert.equal(view.closed, 0);
  await submitInvoice(); assert.equal(view.saved, undefined);
  date = '2026-11-04';
  await submitChild(); assert.equal(calls[0].body.date, '2026-11-03'); assert.equal(calls[1].body.date, '2026-11-03'); assert.equal(calls.length, 2); assert.equal(calls[0].key, calls[1].key); assert.deepEqual(calls[0].body, calls[1].body); assert.equal(child(), null);
  await act(async () => view.root.unmount());
});
test('duplicate rejection stays visible without selecting an item; correction uses a fresh key', async () => {
  const calls = []; const view = await mount({ createItem: async (body, key) => { calls.push({ body, key }); if (calls.length === 1) throw Object.assign(new Error('Item name already exists'), { status: 409 }); return { ...item, name: body.name }; } });
  await click('Create item/service and add line'); await submitChild(); assert.match(child().textContent, /already exists/); assert.equal(child().querySelector('fieldset').disabled, false);
  assert.equal(view.saved, undefined); await change('.inline-party-form [name=name]', 'Different buyer'); await submitChild();
  assert.notEqual(calls[0].key, calls[1].key); await submitInvoice(); assert.equal(view.saved.name, 'New buyer'); assert.equal(view.saved.data.lines[1].description, 'Different buyer');
  await act(async () => view.root.unmount());
});
test('uncertain invoice blocks opening item creation', async () => {
  const view = await mount({ save: async () => { throw new Error('Invoice response lost'); } }); await submitInvoice();
  assert.equal(button('Create item/service and add line').matches(':disabled'), true); await click('Create item/service and add line'); assert.equal(child(), null);
  await act(async () => view.root.unmount());
});
test('stale company, away-and-back, session and unmounted responses cannot populate a newer invoice', async () => {
  for (const switchContext of ['company', 'away-back', 'session']) {
    const scope = createRequestScope('c1'); let token = 'old-session', resolveCreate, updates = 0, calls = 0;
    const createItem = inlineItemCreator({ companyId: 'c1', token, getToken: () => token, isCurrent: scope.capture(), onCreated: () => { updates++; }, api: async (path, options) => { calls++; assert.equal(path, '/companies/c1/records'); assert.equal(options.method, 'POST'); return new Promise(resolve => { resolveCreate = resolve; }); } });
    const view = await mount({ createItem }); await click('Create item/service and add line');
    await act(async () => child().querySelector('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
    if (switchContext === 'session') token = 'new-session'; else { scope.setContext('c2'); if (switchContext === 'away-back') scope.setContext('c1'); }
    await act(async () => view.root.unmount()); await act(async () => resolveCreate(item)); assert.equal(updates, 0);
    await assert.rejects(createItem({ name: 'stale' }, 'key'), /Company or session changed/); assert.equal(calls, 1);
  }
});

test('dirty invoice remains protected after nested cancel; inline keyboard tab stays in item form', async () => {
  const view = await mount(); await change('details.document-notes textarea', 'Unsaved invoice notes'); await click('Create item/service and add line');
  const last = button('Create item and add line'); last.focus();
  await act(async () => last.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })));
  assert.equal(document.activeElement, child().querySelector('button'));
  await act(async () => child().querySelector('button[aria-label=Close]').click());
  await act(async () => window.dispatchEvent(new window.Event('apex-close-editor')));
  assert.ok(button('Discard draft')); assert.equal(view.closed, 0); await act(async () => view.root.unmount());
});
test('viewers and existing or converting documents cannot initiate inline creation', async () => {
  for (const extra of [{ company: { ...company, role: 'viewer' } }, { edit: true }, { source: { data: { lines: [line] } } }, { relatedSource: { data: { lines: [line] } } }]) {
    const view = await mount(extra); const trigger = button('Create item/service and add line');
    if (trigger) { assert.equal(trigger.matches(':disabled'), true); await click('Create item/service and add line'); }
    assert.equal(child(), null); await act(async () => view.root.unmount());
  }
});

test('immediate definitive duplicate rejection unlocks outer Escape and nested Cancel', async () => {
  for (const dismissal of ['escape', 'cancel']) {
    const view = await mount({ createItem: async () => { throw Object.assign(new Error('Item already exists'), { status: 409 }); } });
    await click('Create item/service and add line'); await submitChild();
    if (dismissal === 'escape') await act(async () => child().dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    else await act(async () => [...child().querySelectorAll('button')].find(el => el.textContent === 'Cancel').click());
    assert.equal(child(), null); assert.equal(view.closed, 0); await act(async () => view.root.unmount());
  }
});

test('goods and services use master defaults only on the added line and preserve two edited draft lines', async () => {
  for (const itemType of ['goods', 'services']) {
    let submitted;
    const view = await mount({ draftSeed: { name: 'New buyer', data: {
      party_id: 'retained-party', notes: 'Retain notes', shipping_address: 'Manual delivery',
      lines: [{ ...line, discount_amount: '17.25', item_id: 'old-item' }, { ...line, quantity: '3', discount_percent: '12', rate: '77' }],
    } }, createItem: async body => { submitted = body; return { id: 'created', ...body }; } });
    await change('[aria-label="Item 1 quantity"]', '4');
    await change('[aria-label="Item 1 discount amount"]', '19');
    await click('Create item/service and add line');
    assert.equal(child().querySelector('input[type=file]'), null);
    await change('.inline-party-form [name=name]', 'Reviewed entry');
    await act(async () => child().querySelector('.stock-toggle input').click());
    await change('.inline-party-form [name=item_type]', itemType);
    await change('.inline-party-form [name=sale_rate]', '222.50');
    await change('.inline-party-form [name=gst_rate]', '12');
    await change('.inline-party-form [name=hsn]', '9983');
    await change('.inline-party-form [name=unit]', 'hour');
    if (itemType === 'services') assert.equal(child().querySelector('.stock-toggle input').disabled, true);
    await submitChild(); assert.equal(view.saved, undefined);
    assert.equal(submitted.kind, 'item'); assert.equal(submitted.data.item_type, itemType); assert.equal(submitted.data.track_stock, itemType === 'goods');
    await change('[aria-label="Item 3 quantity"]', '2');
    await change('[aria-label="Item 3 discount mode"]', 'amount');
    await change('[aria-label="Item 3 discount amount"]', '10');
    await submitInvoice();
    const result = view.saved.data;
    assert.equal(result.party_id, 'retained-party'); assert.equal(result.notes, 'Retain notes'); assert.equal(result.shipping_address, 'Manual delivery');
    assert.equal(result.lines[0].item_id, 'old-item'); assert.equal(result.lines[0].quantity, '4'); assert.equal(result.lines[0].discount_amount, '19'); assert.equal(result.lines[0].rate, '125');
    assert.equal(result.lines[1].quantity, '3'); assert.equal(result.lines[1].discount_percent, '12'); assert.equal(result.lines[1].rate, '77');
    assert.equal(result.lines[2].item_id, 'created'); assert.equal(result.lines[2].quantity, '2'); assert.equal(result.lines[2].rate, '222.50');
    assert.equal(result.lines[2].gst_rate, '12'); assert.equal(result.lines[2].tax_treatment, 'taxable'); assert.equal(result.lines[2].discount_amount, '10');
    assert.equal('discount_percent' in result.lines[2], false);
    await act(async () => view.root.unmount());
  }
});
test('only a sole pristine placeholder is reused; edited blank quantity remains untouched', async () => {
  for (const editBlank of [false, true]) {
    const view = await mount({ draftSeed: undefined });
    if (editBlank) await change('[aria-label="Item 1 quantity"]', '7');
    await click('Create item/service and add line'); await submitChild();
    const descriptions = document.querySelectorAll('.document-item-row [name=description]');
    assert.equal(descriptions.length, editBlank ? 2 : 1);
    if (editBlank) { assert.equal(descriptions[0].value, ''); assert.equal(document.querySelector('[aria-label="Item 1 quantity"]').value, '7'); }
    assert.equal(descriptions[descriptions.length - 1].value, 'New service');
    await act(async () => view.root.unmount());
  }
});
test('the 100-line limit prevents creating a master that cannot be added', async () => {
  let calls = 0;
  const view = await mount({ draftSeed: { data: { lines: Array.from({ length: 100 }, () => ({ ...line })) } }, createItem: async () => { calls++; return item; } });
  assert.equal(button('Create item/service and add line').matches(':disabled'), true);
  await click('Create item/service and add line'); assert.equal(child(), null); assert.equal(calls, 0);
  await act(async () => view.root.unmount());
});
test('zero tax treatments and non-GST companies retain the correct added-line tax', async () => {
  for (const [taxMode, taxTreatment, gst] of [['regular', 'exempt', '0'], ['regular', 'non_gst', '0'], ['regular', 'nil_rated', '0'], ['composition', 'taxable', '18'], ['unregistered', 'taxable', '18']]) {
    const view = await mount({ company: { ...company, tax_mode: taxMode }, createItem: async () => ({ ...item, data: { ...item.data, tax_treatment: taxTreatment, gst_rate: gst } }) });
    await click('Create item/service and add line'); await submitChild(); await submitInvoice();
    assert.equal(view.saved.data.lines[1].gst_rate, taxMode === 'regular' ? gst : '0');
    assert.equal(view.saved.data.lines[1].tax_treatment, taxTreatment);
    await act(async () => view.root.unmount());
  }
});
test('late session response cannot append even when the original editor remains mounted', async () => {
  let token = 'before', resolveCreate, updates = 0;
  const createItem = inlineItemCreator({ companyId: 'c1', token, getToken: () => token, isCurrent: () => true,
    onCreated: () => { updates++; }, api: () => new Promise(resolve => { resolveCreate = resolve; }) });
  const view = await mount({ createItem }); await click('Create item/service and add line');
  await act(async () => child().querySelector('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
  token = 'after'; await act(async () => resolveCreate(item));
  assert.equal(updates, 0); assert.ok(child()); assert.equal(document.querySelectorAll('.document-item-row').length, 1);
  await act(async () => view.root.unmount());
});

test('numeric and string zero sale rates are usable and creation focuses the added quantity', async () => {
  for (const rate of [0, '0']) {
  const view = await mount({ createItem: async () => ({ ...item, data: { ...item.data, sale_rate: rate } }) });
  await click('Create item/service and add line'); await submitChild();
  await act(async () => new Promise(resolve => setTimeout(resolve, 5)));
  assert.equal(document.activeElement.getAttribute('aria-label'), 'Item 2 quantity');
  assert.equal(document.querySelector('[aria-label="Item 2 rate"]').value, '0');
  await act(async () => view.root.unmount());
  }
});
