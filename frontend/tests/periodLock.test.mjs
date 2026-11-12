import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';

const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import('react-dom/client');
const temporary = await mkdtemp(resolve('node_modules/.period-lock-tests-'));
const outfile = resolve(temporary, 'lock.mjs');
await build({ entryPoints: ['src/PeriodLock.jsx'], outfile, bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', external: ['react', 'react-dom', 'lucide-react'] });
const PeriodLock = (await import(pathToFileURL(outfile))).default;
const button = label => [...document.querySelectorAll('button')].find(node => node.textContent === label);
async function setDate(value) {
  const input = document.querySelector('input');
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, value);
  await act(async () => input.dispatchEvent(new dom.window.Event('input', { bubbles: true })));
}
const response = data => ({ ok: true, json: async () => data });

test('period lock requires exact-date review, supports cancel, and prevents double confirmation', async () => {
  const root = createRoot(document.getElementById('root'));
  let writes = 0, finish, sent;
  globalThis.fetch = async (url, options) => {
    if (options.method === 'PUT') { writes++; sent = JSON.parse(options.body); return new Promise(resolve => { finish = resolve; }); }
    return response({ locked_through: '2026-03-31' });
  };
  await act(async () => root.render(React.createElement(PeriodLock, { companyId: 'first', role: 'owner' })));
  await setDate('2026-04-30');
  await act(async () => button('Lock through date').click());
  assert.equal(writes, 0);
  assert.match(document.querySelector('[role="alert"]').textContent, /30-Apr-2026/);
  await act(async () => button('Cancel').click());
  assert.equal(writes, 0);
  assert.equal(document.activeElement, document.querySelector('input'));
  await act(async () => button('Lock through date').click());
  await act(async () => { button('Confirm period lock').click(); button('Confirm period lock').click(); });
  assert.equal(writes, 1);
  assert.deepEqual(sent, { locked_through: '2026-04-30' });
  assert.equal(button('Cancel').disabled, true);
  await act(async () => finish(response({ locked_through: '2026-04-30' })));
  assert.match(document.querySelector('[role="status"]').textContent, /30-Apr-2026/);
  assert.equal(button('Lock through date').disabled, true);
  await act(async () => root.unmount());
});

test('failed load is not represented as an unlocked period and can be retried', async () => {
  const root = createRoot(document.getElementById('root'));
  let calls = 0;
  globalThis.fetch = async () => ++calls === 1 ? { ok: false, json: async () => ({ detail: 'Synthetic unavailable' }) } : response({ locked_through: '2026-03-31' });
  await act(async () => root.render(React.createElement(PeriodLock, { companyId: 'first', role: 'owner' })));
  assert.match(document.body.textContent, /Not available/);
  assert.equal(button('Lock through date').disabled, true);
  await act(async () => button('Retry loading').click());
  assert.match(document.body.textContent, /31-Mar-2026/);
  await act(async () => root.unmount());
});

test('late lock response cannot change another company', async () => {
  const root = createRoot(document.getElementById('root'));
  let finish;
  globalThis.fetch = async (url, options) => options.method === 'PUT' ? new Promise(resolve => { finish = resolve; }) : response({ locked_through: '' });
  await act(async () => root.render(React.createElement(PeriodLock, { companyId: 'first', role: 'owner' })));
  await setDate('2026-04-30');
  await act(async () => button('Lock through date').click());
  await act(async () => button('Confirm period lock').click());
  await act(async () => root.render(React.createElement(PeriodLock, { companyId: 'second', role: 'owner' })));
  await act(async () => finish(response({ locked_through: '2026-04-30' })));
  assert.match(document.body.textContent, /No date set/);
  assert.equal(document.querySelector('[role="status"]'), null);
  await act(async () => root.unmount());
});

test.after(async () => { dom.window.close(); await rm(temporary, { recursive: true, force: true }); });
