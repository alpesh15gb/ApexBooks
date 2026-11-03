import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { inlinePartyCreator } from '../src/inlineParty.js';
import { createRequestScope } from '../src/requestScope.js';
const temp = await mkdtemp(resolve('node_modules/.inline-party-tests-'));
await build({ entryPoints: ['src/RecordEditor.jsx'], outfile: resolve(temp, 'editor.mjs'), bundle: true, platform: 'node', format: 'esm', external: ['react', 'react-dom', 'lucide-react'] });
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import('react-dom/client');
const Editor = (await import(pathToFileURL(resolve(temp, 'editor.mjs')))).default;
after(async () => { dom.window.close(); await rm(temp, { recursive: true, force: true }); });
const Modal = ({ children, close }) => React.createElement('section', { onKeyDown: e => { if (e.key === 'Escape') close(); } }, children);
const line = { description: 'Draft service', quantity: '2', rate: '125', gst_rate: '0', tax_treatment: 'nil_rated' };
const company = { role: 'owner', tax_mode: 'regular', state_code: '27', name: 'Synthetic Books' };
const party = { id: 'party-new', kind: 'party', name: 'New buyer', data: { address: 'Billing road', shipping_address: 'Default delivery', phone: '12345', gstin: '29ABCDE1234F1Z5' } };
const button = text => [...document.querySelectorAll('button')].find(el => el.textContent === text);
const child = () => document.querySelector('.inline-party-form');
async function click(text) { await act(async () => button(text).click()); }
async function change(selector, value) {
  await act(async () => { const el = document.querySelector(selector); const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value); el.dispatchEvent(new window.Event('input', { bubbles: true })); });
}
const submitChild = () => act(async () => child().querySelector('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
async function mount(extra = {}) {
  const root = createRoot(document.getElementById('root')); let saved, closed = 0;
  await act(async () => root.render(React.createElement(Editor, {
    kind: 'sales_invoice', company, companyId: 'c1', records: [], features: ['party_shipping_address'],
    draftSeed: { name: 'New buyer', data: { lines: [line], shipping_address: 'Manual delivery', due_date: '2026-12-01', notes: 'Keep my notes' } },
    api: async path => path.endsWith('bank-accounts') ? [] : { amount: '250', data: { lines: [] } },
    Modal, labels: { sales_invoice: 'Sales invoices' }, documentKinds: ['sales_invoice'], money: String, today: () => '2026-11-03',
    createParty: async () => party, save: payload => { saved = payload; }, close: () => { closed++; }, ...extra,
  })));
  return { root, get saved() { return saved; }, get closed() { return closed; } };
}
const invoiceForm = () => document.querySelector('form.document-form');
const submitInvoice = () => act(async () => invoiceForm().dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));

test('cancel keeps the same invoice mounted, restores focus and preserves draft fields', async () => {
  const view = await mount(); const original = invoiceForm();
  await change('details.document-notes textarea', 'Keep my edited notes');
  await click('Create new party'); assert.equal(document.activeElement.name, 'name');
  assert.equal(invoiceForm(), original); assert.equal(original.parentElement.hidden, true);
  await change('.inline-party-form [name=name]', 'Do not save');
  await act(async () => child().dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
  await act(async () => new Promise(resolve => setTimeout(resolve, 5)));
  assert.equal(child(), null); assert.equal(document.activeElement, button('Create new party'));
  await submitInvoice(); assert.equal(view.saved.name, 'New buyer'); assert.equal(view.saved.data.lines[0].rate, '125');
  assert.equal(view.saved.data.shipping_address, 'Manual delivery'); assert.equal(view.saved.data.due_date, '2026-12-01'); assert.equal(view.saved.data.notes, 'Keep my edited notes');
  await act(async () => view.root.unmount());
});
test('create uses returned identity without posting invoice or overwriting manual delivery, lines or due date', async () => {
  let calls = 0; const view = await mount({ createParty: async body => { calls++; assert.equal(body.name, 'New buyer'); return party; } });
  const original = invoiceForm(); await click('Create new party'); await submitInvoice(); assert.equal(view.saved, undefined);
  await submitChild(); assert.equal(calls, 1); assert.equal(child(), null); assert.equal(invoiceForm(), original); assert.equal(view.saved, undefined);
  assert.ok(document.querySelector('datalist#apex-party-options option[value="New buyer"]'));
  await submitInvoice(); assert.equal(view.saved.data.party_id, party.id); assert.equal(view.saved.data.party_address, 'Billing road');
  assert.equal(view.saved.data.party_phone, '12345'); assert.equal(view.saved.data.place_of_supply, '29');
  assert.equal(view.saved.data.shipping_address, 'Manual delivery'); assert.equal(view.saved.data.due_date, '2026-12-01'); assert.equal(view.saved.data.lines[0].quantity, '2');
  await act(async () => view.root.unmount());
});
test('uncertain party save freezes details, blocks dismiss and invoice submit, and retries exact body/key only once', async () => {
  const calls = []; let rejectFirst; let date = "2026-11-03";
  const view = await mount({ today: () => date, createParty: (body, key) => { calls.push({ body, key }); return calls.length === 1 ? new Promise((_, reject) => { rejectFirst = reject; }) : Promise.resolve(party); } });
  await click('Create new party');
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
test('duplicate rejection stays visible without selecting a party; correction uses a fresh key', async () => {
  const calls = []; const view = await mount({ createParty: async (body, key) => { calls.push({ body, key }); if (calls.length === 1) throw Object.assign(new Error('Party name already exists'), { status: 409 }); return { ...party, name: body.name }; } });
  await click('Create new party'); await submitChild(); assert.match(child().textContent, /already exists/); assert.equal(child().querySelector('fieldset').disabled, false);
  assert.equal(view.saved, undefined); await change('.inline-party-form [name=name]', 'Different buyer'); await submitChild();
  assert.notEqual(calls[0].key, calls[1].key); await submitInvoice(); assert.equal(view.saved.name, 'Different buyer');
  await act(async () => view.root.unmount());
});
test('uncertain invoice blocks opening party creation', async () => {
  const view = await mount({ save: async () => { throw new Error('Invoice response lost'); } }); await submitInvoice();
  assert.equal(button('Create new party').matches(':disabled'), true); await click('Create new party'); assert.equal(child(), null);
  await act(async () => view.root.unmount());
});
test('stale company, away-and-back, session and unmounted responses cannot populate a newer invoice', async () => {
  for (const switchContext of ['company', 'away-back', 'session']) {
    const scope = createRequestScope('c1'); let token = 'old-session', resolveCreate, updates = 0, calls = 0;
    const createParty = inlinePartyCreator({ companyId: 'c1', token, getToken: () => token, isCurrent: scope.capture(), onCreated: () => { updates++; }, api: async (path, options) => { calls++; assert.equal(path, '/companies/c1/records'); assert.equal(options.method, 'POST'); return new Promise(resolve => { resolveCreate = resolve; }); } });
    const view = await mount({ createParty }); await click('Create new party');
    await act(async () => child().querySelector('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
    if (switchContext === 'session') token = 'new-session'; else { scope.setContext('c2'); if (switchContext === 'away-back') scope.setContext('c1'); }
    await act(async () => view.root.unmount()); await act(async () => resolveCreate(party)); assert.equal(updates, 0);
    await assert.rejects(createParty({ name: 'stale' }, 'key'), /Company or session changed/); assert.equal(calls, 1);
  }
});

test('dirty invoice remains protected after nested cancel; inline keyboard tab stays in party form', async () => {
  const view = await mount(); await change('details.document-notes textarea', 'Unsaved invoice notes'); await click('Create new party');
  const last = button('Create and use party'); last.focus();
  await act(async () => last.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })));
  assert.equal(document.activeElement, child().querySelector('button'));
  await act(async () => child().querySelector('button[aria-label=Close]').click());
  await act(async () => window.dispatchEvent(new window.Event('apex-close-editor')));
  assert.ok(button('Discard draft')); assert.equal(view.closed, 0); await act(async () => view.root.unmount());
});
test('viewers and existing or converting documents cannot initiate inline creation', async () => {
  for (const extra of [{ company: { ...company, role: 'viewer' } }, { edit: true }, { source: { data: { lines: [line] } } }, { relatedSource: { data: { lines: [line] } } }]) {
    const view = await mount(extra); const trigger = button('Create new party');
    if (trigger) { assert.equal(trigger.matches(':disabled'), true); await click('Create new party'); }
    assert.equal(child(), null); await act(async () => view.root.unmount());
  }
});

test('immediate definitive duplicate rejection unlocks outer Escape and nested Cancel', async () => {
  for (const dismissal of ['escape', 'cancel']) {
    const view = await mount({ createParty: async () => { throw Object.assign(new Error('Party already exists'), { status: 409 }); } });
    await click('Create new party'); await submitChild();
    if (dismissal === 'escape') await act(async () => child().dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    else await act(async () => [...child().querySelectorAll('button')].find(el => el.textContent === 'Cancel').click());
    assert.equal(child(), null); assert.equal(view.closed, 0); await act(async () => view.root.unmount());
  }
});
