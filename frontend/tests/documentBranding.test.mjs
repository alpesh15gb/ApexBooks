import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { hasPendingPostings } from '../src/postingRegistry.js';

const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import('react-dom/client');
const temporary = await mkdtemp(resolve('node_modules/.branding-tests-'));
const outfile = resolve(temporary, 'branding.mjs');
await build({ entryPoints: ['src/DocumentBranding.jsx'], outfile, bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', external: ['react', 'react-dom', 'lucide-react'], plugins: [{ name: 'registry', setup(build) { build.onResolve({ filter: /postingRegistry\.js$/ }, () => ({ path: resolve('src/postingRegistry.js'), external: true })); } }] });
const Branding = (await import(pathToFileURL(outfile))).default;
const response = data => ({ ok: true, json: async () => data });
const submit = () => document.querySelector('form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }));
const account = () => [...document.querySelectorAll('label')].find(node => node.textContent.startsWith('Bank account number')).querySelector('input');

test('branding saves freeze draft fields and prevent duplicate requests', async () => {
  const root = createRoot(document.getElementById('root'));
  let finish, writes = 0;
  globalThis.fetch = async (url, options) => {
    if (options.method) { writes++; return new Promise(resolve => { finish = resolve; }); }
    return response({ account_number: 'synthetic-account' });
  };
  await act(async () => root.render(React.createElement(Branding, { companyId: 'first', role: 'owner' })));
  await act(async () => { submit(); submit(); });
  assert.equal(writes, 1);
  assert.equal(hasPendingPostings(), true);
  assert.equal(document.querySelector('fieldset').disabled, true);
  await act(async () => finish(response({ account_number: 'synthetic-account' })));
  assert.equal(document.querySelector('fieldset').disabled, false);
  assert.equal(hasPendingPostings(), false);
  await act(async () => root.unmount());
});

test('late branding response cannot populate a different company bank details', async () => {
  const root = createRoot(document.getElementById('root'));
  let finish;
  globalThis.fetch = async (url, options) => options.method
    ? new Promise(resolve => { finish = resolve; })
    : response({ account_number: url.includes('/first/') ? 'first-synthetic-account' : 'second-synthetic-account' });
  await act(async () => root.render(React.createElement(Branding, { companyId: 'first', role: 'owner' })));
  await act(async () => submit());
  await act(async () => root.render(React.createElement(Branding, { companyId: 'second', role: 'owner' })));
  await act(async () => finish(response({ account_number: 'first-synthetic-account' })));
  assert.equal(account().value, 'second-synthetic-account');
  assert.equal(document.querySelector('[role="status"]'), null);
  await act(async () => root.unmount());
});

test('failed branding save preserves the draft and permits retry', async () => {
  const root = createRoot(document.getElementById('root'));
  globalThis.fetch = async (url, options) => options.method ? { ok: false, json: async () => ({ detail: 'Synthetic save unavailable' }) } : response({ account_number: 'synthetic-account' });
  await act(async () => root.render(React.createElement(Branding, { companyId: 'first', role: 'owner' })));
  await act(async () => submit());
  assert.equal(account().value, 'synthetic-account');
  assert.equal(document.querySelector('[role="alert"]').textContent, 'Synthetic save unavailable');
  assert.equal(document.querySelector('fieldset').disabled, false);
  assert.equal(hasPendingPostings(), false);
  await act(async () => root.unmount());
});

test.after(async () => { dom.window.close(); await rm(temporary, { recursive: true, force: true }); });
