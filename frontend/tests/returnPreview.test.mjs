import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
const temp = await mkdtemp(resolve('node_modules/.return-preview-tests-'));
await build({ entryPoints: ['src/DocumentWorkbench.jsx'], outfile: resolve(temp, 'preview.mjs'), bundle: true, platform: 'node', format: 'esm', external: ['react', 'react-dom', 'lucide-react'] });
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import('react-dom/client');
const { useDocumentPreview } = await import(pathToFileURL(resolve(temp, 'preview.mjs')));
after(async () => { dom.window.close(); await rm(temp, { recursive: true, force: true }); });
test('linked return preview includes original source and displays canonical residual total', async () => {
  const calls = [];
  const api = async (path, options) => { calls.push({ path, body: JSON.parse(options.body) }); return { amount: '106.18', data: {} }; };
  function Preview() {
    const result = useDocumentPreview({ api, companyId: 'company-a', kind: 'credit_note', enabled: true, recordId: 'existing-return-a',
      form: { date: '2026-04-03', applied_to: 'source-a', place_of_supply: '36' },
      lines: [{ description: 'Synthetic service', quantity: 1, rate: '99.99', gst_rate: 18, discount_percent: 10 }] });
    return React.createElement('output', null, result?.amount ?? 'Loading');
  }
  const root = createRoot(document.getElementById('root'));
  try {
    await act(async () => root.render(React.createElement(Preview)));
    await act(async () => new Promise(resolve => setTimeout(resolve, 360)));
    assert.equal(calls.length, 1);
    assert.equal(calls[0].path, '/companies/company-a/documents/preview');
    assert.equal(calls[0].body.data.applied_to, 'source-a');
    assert.equal(calls[0].body.data.preview_record_id, 'existing-return-a');
    assert.equal(document.querySelector('output').textContent, '106.18');
  } finally { await act(async () => root.unmount()); }
});
