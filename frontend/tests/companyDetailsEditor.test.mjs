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
const temporary = await mkdtemp(resolve('node_modules/.company-editor-tests-'));
const outfile = resolve(temporary, 'editor.mjs');
await build({ entryPoints: ['src/CompanyDetailsEditor.jsx'], outfile, bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', external: ['react', 'react-dom', 'lucide-react'], plugins: [{ name: 'registry', setup(build) { build.onResolve({ filter: /postingRegistry\.js$/ }, () => ({ path: resolve('src/postingRegistry.js'), external: true })); } }] });
const Editor = (await import(pathToFileURL(outfile))).default;
const company = { id: 'first', name: 'Synthetic company', tax_mode: 'unregistered', role: 'owner', state_code: '27' };
const submit = () => document.querySelector('form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }));
const button = label => [...document.querySelectorAll('button')].find(node => node.textContent === label);
async function changeName(value) {
  const input = document.querySelector('input[name="name"]');
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, value);
  await act(async () => input.dispatchEvent(new dom.window.Event('input', { bubbles: true })));
}

test('company edit prevents duplicate submission and dismissal while saving', async () => {
  const root = createRoot(document.getElementById('root'));
  let finish, calls = 0, saved = 0;
  globalThis.fetch = () => { calls++; return new Promise(resolve => { finish = resolve; }); };
  await act(async () => root.render(React.createElement(Editor, { company, onSaved: () => saved++ })));
  await act(async () => button('Edit company details').click());
  await act(async () => { submit(); submit(); });
  assert.equal(calls, 1);
  assert.equal(hasPendingPostings(), true);
  assert.equal(document.querySelector('fieldset').disabled, true);
  await act(async () => {
    button('Cancel').click();
    document.querySelector('.overlay').dispatchEvent(new dom.window.MouseEvent('mousedown', { bubbles: true }));
  });
  assert.ok(document.querySelector('form'));
  await act(async () => finish({ ok: true, json: async () => company }));
  assert.equal(saved, 1);
  assert.equal(hasPendingPostings(), false);
  assert.equal(document.querySelector('form'), null);
  await act(async () => root.unmount());
});

test('late save cannot replace a different company or dismiss its editor', async () => {
  const root = createRoot(document.getElementById('root'));
  let finish, saved = 0;
  globalThis.fetch = () => new Promise(resolve => { finish = resolve; });
  const onSaved = () => saved++;
  await act(async () => root.render(React.createElement(Editor, { company, onSaved })));
  await act(async () => button('Edit company details').click());
  await act(async () => submit());
  await act(async () => root.render(React.createElement(Editor, { company: { ...company, id: 'second', name: 'Second company' }, onSaved })));
  await act(async () => button('Edit company details').click());
  await act(async () => finish({ ok: true, json: async () => company }));
  assert.equal(saved, 0);
  assert.equal(document.querySelector('input[name="name"]').value, 'Second company');
  await act(async () => root.unmount());
});

test('company edits require explicit discard and preserve entered values after failure', async () => {
  const root = createRoot(document.getElementById('root'));
  globalThis.fetch = async () => ({ ok: false, json: async () => ({ detail: 'Synthetic save failure' }) });
  await act(async () => root.render(React.createElement(Editor, { company, onSaved: () => {} })));
  await act(async () => button('Edit company details').click());
  await changeName('Updated company');
  await act(async () => button('Cancel').click());
  assert.ok(button('Keep editing'));
  await act(async () => button('Keep editing').click());
  assert.equal(document.querySelector('input[name="name"]').value, 'Updated company');
  await act(async () => submit());
  assert.equal(document.querySelector('[role="alert"]').textContent, 'Synthetic save failure');
  assert.equal(document.querySelector('fieldset').disabled, false);
  assert.equal(document.querySelector('input[name="name"]').value, 'Updated company');
  await act(async () => button('Cancel').click());
  await act(async () => button('Discard changes').click());
  assert.equal(document.querySelector('form'), null);
  await act(async () => root.unmount());
});

test('registered company modes require GSTIN and state while unregistered books do not', async () => {
  const root = createRoot(document.getElementById('root'));
  for (const tax_mode of ['regular', 'composition', 'unregistered']) {
    await act(async () => root.render(React.createElement(Editor, { company: { ...company, id: tax_mode, tax_mode }, onSaved: () => {} })));
    await act(async () => button('Edit company details').click());
    const registered = tax_mode !== 'unregistered';
    const gstin = document.querySelector('input[name="gstin"]');
    assert.equal(!!gstin, registered);
    if (registered) assert.equal(gstin.required, true);
    assert.equal(document.querySelector('input[name="state_code"]').required, registered);
  }
  await act(async () => root.unmount());
});

test.after(async () => { dom.window.close(); await rm(temporary, { recursive: true, force: true }); });
