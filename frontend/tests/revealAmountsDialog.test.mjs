import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { JSDOM } from 'jsdom';
import { build } from 'esbuild';
import React, { act } from 'react';

const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import('react-dom/client');
const temp = await mkdtemp(resolve('node_modules/.reveal-amounts-'));
const file = resolve(temp, 'dialog.mjs');
await build({ entryPoints: [resolve('src/RevealAmountsDialog.jsx')], outfile: file, bundle: true, platform: 'node', format: 'esm', loader: { '.jsx': 'jsx' }, external: ['react', 'react-dom', 'lucide-react'], jsx: 'transform' });
const Dialog = (await import(pathToFileURL(file))).default;
test.after(() => rm(temp, { recursive: true, force: true }));

async function mount(api) {
  const events = { revealed: 0, closed: 0 };
  const root = createRoot(document.getElementById('root'));
  await act(async () => root.render(React.createElement(Dialog, { api, onRevealed: () => { events.revealed++; }, onClose: () => { events.closed++; } })));
  const type = async value => act(async () => {
    const input = document.querySelector('input[type=password]');
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, value);
    input.dispatchEvent(new window.Event('input', { bubbles: true }));
  });
  const submit = async () => act(async () => { document.querySelector('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })); });
  return { events, type, submit, input: () => document.querySelector('input[type=password]'), unmount: () => act(async () => root.unmount()) };
}

test('a correct password reveals once and sends it only to the password check', async () => {
  const calls = [];
  const view = await mount(async (path, options) => { calls.push({ path, body: JSON.parse(options.body), method: options.method }); return { verified: true }; });
  await view.type('right-password');
  await view.submit();
  assert.deepEqual(calls, [{ path: '/auth/verify-password', method: 'POST', body: { password: 'right-password' } }]);
  assert.equal(view.events.revealed, 1);
  await view.unmount();
});

test('an empty password is refused locally without calling the server', async () => {
  let called = 0;
  const view = await mount(async () => { called++; return {}; });
  await view.submit();
  assert.equal(called, 0);
  assert.match(document.querySelector('[role=alert]').textContent, /Enter your password/);
  assert.equal(view.events.revealed, 0);
  await view.unmount();
});

test('a wrong password keeps amounts hidden, clears the field and explains', async () => {
  const view = await mount(async () => { throw Object.assign(new Error('Password is incorrect'), { status: 403 }); });
  await view.type('nope-nope');
  await view.submit();
  assert.equal(view.events.revealed, 0);
  assert.equal(view.input().value, '');
  assert.match(document.querySelector('[role=alert]').textContent, /not correct/);
  assert.equal(view.input().getAttribute('aria-invalid'), 'true');
  await view.unmount();
});

test('too many attempts and network failures never reveal', async () => {
  for (const [status, pattern] of [[429, /Too many attempts/], [0, /connection|reach/i]]) {
    const view = await mount(async () => { throw Object.assign(new Error('Cannot reach Apex Books. Check your connection.'), { status }); });
    await view.type('whatever-1');
    await view.submit();
    assert.equal(view.events.revealed, 0);
    assert.match(document.querySelector('[role=alert]').textContent, pattern);
    await view.unmount();
  }
});

test('a server without the check does not strand the user behind masked figures', async () => {
  const view = await mount(async () => { throw Object.assign(new Error('Not found'), { status: 404 }); });
  await view.type('anything-1');
  await view.submit();
  assert.equal(view.events.revealed, 1);
  await view.unmount();
});

test('Escape and Cancel close the dialog without revealing', async () => {
  const view = await mount(async () => ({ verified: true }));
  await act(async () => document.querySelector('form').dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
  await act(async () => [...document.querySelectorAll('button')].find(b => b.textContent === 'Cancel').click());
  assert.equal(view.events.closed, 2);
  assert.equal(view.events.revealed, 0);
  await view.unmount();
});
