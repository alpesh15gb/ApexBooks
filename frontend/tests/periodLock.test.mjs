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

for (const recoveredDate of ['2026-04-30', '2026-05-31']) test(`unknown period lock stays frozen until current date ${recoveredDate} is verified`, async t => {
  const root = createRoot(document.getElementById('root')); t.after(async () => act(async () => root.unmount()));
  let writes = 0, visibleDate = '2026-03-31', readFailure = false;
  globalThis.fetch = async (url, options) => {
    if (options.method === 'PUT') { writes++; throw new TypeError('Synthetic lost lock response'); }
    if (readFailure) throw new TypeError('Synthetic read failed');
    return response({locked_through: visibleDate});
  };
  await act(async () => root.render(React.createElement(PeriodLock, {companyId:'first', role:'owner'})));
  await setDate('2026-04-30'); await act(async () => button('Lock through date').click());
  await act(async () => button('Confirm period lock').click());
  assert.equal(writes, 1); assert.equal(button('Cancel').disabled, true);
  assert.match(document.body.textContent, /not confirmed/i); assert.doesNotMatch(document.querySelectorAll('p')[1].textContent, /31-Mar-2026/);
  await act(async () => button('Check current lock').click()); assert.equal(writes, 1); assert.equal(button('Cancel').disabled, true);
  readFailure = true; await act(async () => button('Check current lock').click()); assert.equal(button('Cancel').disabled, true);
  readFailure = false; visibleDate = recoveredDate;
  await act(async () => root.render(React.createElement(PeriodLock, {companyId:'first', role:'viewer'})));
  assert.equal(button('Retry original lock'), undefined); await act(async () => button('Check current lock').click());
  assert.equal(writes, 1); assert.match(document.querySelector('[role=status]').textContent, recoveredDate.endsWith('04-30') ? /30-Apr-2026/ : /31-May-2026/);
});

test('unknown lock retries only its reviewed date and is single-flight', async t => {
 const root=createRoot(document.getElementById('root'));t.after(async()=>act(async()=>root.unmount()));const bodies=[];let finish;
 globalThis.fetch=async(url,options)=>{if(options.method!=='PUT')return response({locked_through:''});bodies.push(JSON.parse(options.body));if(bodies.length===1)return {ok:false,status:503,json:async()=>({detail:'Synthetic unknown save'})};return new Promise(resolve=>{finish=resolve});};
 await act(async()=>root.render(React.createElement(PeriodLock,{companyId:'a',role:'owner'})));await setDate('2026-04-30');await act(async()=>button('Lock through date').click());await act(async()=>button('Confirm period lock').click());assert.match(document.body.textContent,/Recovery is kept only in this tab/);await setDate('2026-12-31');await act(async()=>{button('Retry original lock').click();button('Retry original lock').click();});assert.equal(bodies.length,2);assert.deepEqual(bodies[1],{locked_through:'2026-04-30'});await act(async()=>finish(response({locked_through:'2026-04-30'})));assert.equal(button('Check current lock'),undefined);assert.match(document.querySelector('[role=status]').textContent,/30-Apr-2026/);
});

test.after(async () => { dom.window.close(); await rm(temporary, { recursive: true, force: true }); });
