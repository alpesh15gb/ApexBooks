import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import { act } from 'react';

test('a signed-in account with no companies can create its first company', async () => {
  const temporary = await mkdtemp(resolve('node_modules/.onboarding-tests-'));
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, MutationObserver: dom.window.MutationObserver, requestAnimationFrame: cb => setTimeout(cb, 0), IS_REACT_ACT_ENVIRONMENT: true });
  window.scrollTo = () => {};
  localStorage.token = 'synthetic-token';
  localStorage.companyId = 'previous-account-company';
  globalThis.ResizeObserver = class { observe() {} disconnect() {} };
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async path => ({ ok: true, json: async () => path === '/api/companies' ? [] : {} });
  try {
    const outfile = resolve(temporary, 'app.mjs');
    await build({ entryPoints: ['src/main.jsx'], outfile, bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', external: ['react', 'react-dom', 'react-dom/client', 'lucide-react'], loader: { '.css': 'empty' } });
    await act(async () => { await import(pathToFileURL(outfile)); });
    assert.match(document.body.textContent, /Add a company/);
    assert.match(document.body.textContent, /Set up your first company/);
    assert.ok(document.querySelector('[role="dialog"]'));
  } finally {
    globalThis.fetch = oldFetch;
    dom.window.close();
    await rm(temporary, { recursive: true, force: true });
  }
});
