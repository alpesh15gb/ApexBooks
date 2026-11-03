import { CORE_ENHANCEMENTS } from '../src/capabilities.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import { act } from 'react';

async function workspace(role, verify, additional = [], capabilities = CORE_ENHANCEMENTS, { masterError = null, recordsUnavailable = false } = {}) {
  const temporary = await mkdtemp(resolve('node_modules/.workspace-tests-'));
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, MutationObserver: dom.window.MutationObserver, requestAnimationFrame: cb => setTimeout(cb, 0), ResizeObserver: class { observe() {} disconnect() {} }, IS_REACT_ACT_ENVIRONMENT: true });
  Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});
  window.scrollTo = () => {}; window.HTMLElement.prototype.scrollIntoView = () => {};
  localStorage.token = 'synthetic-token';
  const company = { id: 'company', name: 'Synthetic company', state_code: '27', tax_mode: 'unregistered', role };
  const invoice = { id: 'invoice', kind: 'sales_invoice', name: 'Synthetic customer', number: 'INV-1', date: '2026-11-02', posted: true, amount: '100', outstanding: '40', data: { lines: [{ description: 'Service', quantity: '1', rate: '100', gst_rate: '0' }], place_of_supply: '27' } };
  const posts = [], requests = [], masterWrites = []; const state = { records: null, preferences: null, summary: null, post: null };
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async (path, options = {}) => {
    requests.push(path);
    let data;
    if (path === '/api/capabilities') {
      const advertised = typeof capabilities === 'function' ? capabilities() : capabilities;
      if (advertised === null || advertised?.status) return { ok: false, status: advertised?.status || 404, json: async () => ({ detail: 'Synthetic capability check unavailable' }) };
      data = { api_version: 'synthetic', capabilities_version: 1, supported_features: advertised };
    }
    else if (path === '/api/companies') data = [company, { ...company, id: 'other-company', name: 'Other company' }];
    else if (path.includes('/records?')) { if (recordsUnavailable === 'empty') return {ok:true,json:async()=>[]}; if (recordsUnavailable) return {ok:false,status:503,json:async()=>({detail:'History unavailable'})}; if (state.records) return state.records(path); data = [invoice, ...additional]; }
    else if (path.endsWith('/records/invoice')) { const { outstanding, ...detail } = invoice; data = detail; }
    else if (additional.some(row => path.endsWith('/records/' + row.id))) data = additional.find(row => path.endsWith('/records/' + row.id));
    else if (path.includes('/masters/') && options.method === 'PUT') {
      masterWrites.push(JSON.parse(options.body));
      if (masterError) return { ok: false, status: 409, json: async () => ({ detail: masterError }) };
      data = { id: 'master-saved' };
    }
    else if (path.endsWith('/records') && options.method === 'POST') { posts.push(JSON.parse(options.body)); if(state.post) return state.post(path,options); data = { id: 'saved' }; }
    else if (path.endsWith('/documents/preview')) data = {amount:'100',data:{cgst:'0',sgst:'0',igst:'0'}};
    else if (path.endsWith('/bank-accounts')) data = [{ id: 'default', name: 'Synthetic bank' }];
    else if (path.endsWith('/preferences')) { if(state.preferences) return state.preferences(path, options); data = { document_template: 'vintage' }; }
    else if (path.includes('/reports/summary')) data = state.summary || {sales:'100',receivables:'40',payables:'0'};
    else if (path.includes('/reports/financial')) data = {accounts:[],net_profit:'200',income:'1000',expenses:'800'};
    else if (path.includes('/reports/gst-payable')) data = {cash_total:'0',output:{},book_itc:{}};
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
    await verify({ click, posts, invoice, dom, requests, masterWrites, state });
  } finally {
    globalThis.fetch = previousFetch;
    dom.window.close();
    await rm(temporary, { recursive: true, force: true });
  }
}



const recordsCount=requests=>requests.filter(path=>path.includes('/records?')).length;
const summariesCount=requests=>requests.filter(path=>path.includes('/reports/summary?')).length;
const recordsResponse=rows=>({ok:true,json:async()=>rows});
const focus=()=>act(async()=>window.dispatchEvent(new window.Event('focus')));

test('focus skipped during payment modal catches up exactly once after normal cancellation',async()=>workspace('owner',async({click,state,invoice,requests})=>{
 await click('Sales invoices'); await click('Collect payment');
 const before=recordsCount(requests);
 state.records=()=>recordsResponse([{...invoice,outstanding:'0'},{...invoice,id:'remote-invoice',name:'Remote invoice',number:'INV-REMOTE'}]);
 await focus();assert.equal(recordsCount(requests),before);
 await click('Cancel');
 assert.equal(document.querySelector('.modal'),null);
 await act(async()=>new Promise(resolve=>setTimeout(resolve,100)));
 assert.equal(recordsCount(requests),before+1,'one catch-up after modal closes');
 assert.match(document.querySelector('.register').textContent,/Remote invoice/);
 assert.match(document.querySelector('.workspace-sync-line').textContent,/Company data loaded/);
 await click('Refresh');
 assert.equal(recordsCount(requests),before+2);
 assert.match(document.querySelector('.register').textContent,/Remote invoice/);
}));

test('throttled visibility events coalesce to exactly one trailing catch-up',async()=>workspace('owner',async({click,state,invoice,requests})=>{
 await click('Sales invoices');await focus();const before=recordsCount(requests);
 state.records=()=>recordsResponse([{...invoice,id:'remote-invoice',name:'Remote invoice',number:'INV-REMOTE'}]);
 await act(async()=>{for(let i=0;i<4;i++) document.dispatchEvent(new window.Event('visibilitychange'));});
 assert.equal(recordsCount(requests),before);
 assert.match(document.querySelector('.workspace-sync-line').textContent,/Refresh pending/);
 await act(async()=>new Promise(resolve=>setTimeout(resolve,1600)));
 assert.equal(recordsCount(requests),before+1,'one trailing refresh after throttle expires');
 assert.match(document.querySelector('.register').textContent,/Remote invoice/);
 assert.match(document.querySelector('.workspace-sync-line').textContent,/Company data loaded/);
 assert.match(document.querySelector('.register').textContent,/Remote invoice/);
}));

test('failed history refresh labels independently refreshed summaries and old collections as stale',async()=>workspace('owner',async({click,state,requests,invoice})=>{
 const beforeRecords=recordsCount(requests), beforeSummaries=summariesCount(requests);
 assert.match(document.querySelector('.collection-numbers').textContent,/40/);
 state.summary={sales:'200',receivables:'140',payables:'0'};
 state.records=()=>({ok:false,status:503,json:async()=>({detail:'Synthetic history unavailable'})});
 await click('Refresh');
 assert.equal(recordsCount(requests),beforeRecords+1);assert.equal(summariesCount(requests),beforeSummaries+1);
 assert.match(document.querySelector('.workspace-sync-line').textContent,/Refresh needed/);
 assert.match(document.querySelector('.books-status').textContent,/Company history needs refresh/);
 assert.match(document.body.textContent,/Summary reports and history refresh separately/);
 assert.match(document.querySelector('.overview-metric').textContent,/200/);
 assert.match(document.querySelector('.collection-numbers').textContent,/40/);
 state.records=()=>recordsResponse([{...invoice,outstanding:'140',amount:'200'}]);
 await click('Refresh');
 assert.match(document.querySelector('.books-status').textContent,/Books loaded/);
 assert.doesNotMatch(document.querySelector('.workspace-sync-line').textContent,/Refresh needed|may be out of date/);
 assert.match(document.querySelector('.collection-numbers').textContent,/140/);
}));

test('control: hidden page does not fetch; unthrottled visible focus refreshes remote invoice/payment and dashboard totals',async()=>workspace('owner',async({state,invoice,requests,click})=>{
 const beforeRecords=recordsCount(requests),beforeSummary=summariesCount(requests);
 state.records=()=>recordsResponse([{...invoice,outstanding:'0'},{...invoice,id:'remote-invoice',number:'INV-REMOTE',name:'Remote invoice',outstanding:'100'},{id:'remote-payment',kind:'payment_in',name:'Synthetic customer',number:'PAY-REMOTE',date:'2026-11-03',posted:true,amount:'40',data:{}}]);
 state.summary={sales:'200',receivables:'100',payables:'0'};
 Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});
 await focus();assert.equal(recordsCount(requests),beforeRecords);
 Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});
 await act(async()=>document.dispatchEvent(new window.Event('visibilitychange')));
 assert.equal(recordsCount(requests),beforeRecords+1);assert.equal(summariesCount(requests),beforeSummary+1);
 assert.match(document.querySelector('.overview-metric').textContent,/200/);
 assert.match(document.querySelector('.collection-numbers').textContent,/Outstanding.*100/);
 assert.match(document.querySelector('.activity-insight').textContent,/PAY-REMOTE/);
 await click('Sales invoices');assert.match(document.querySelector('.register').textContent,/Remote invoice/);
}));

for(const change of ['company','account-event','account-missed-event']) test(`queued trailing refresh is discarded on ${change} switch`,async()=>workspace('owner',async({click,requests})=>{
 await click('Sales invoices');await focus();const before=recordsCount(requests);
 await focus();assert.match(document.querySelector('.workspace-sync-line').textContent,/Refresh pending/);
 if(change==='company') {
  const picker=document.querySelector('[aria-label="Choose company"]');
  await act(async()=>{picker.value='other-company';picker.dispatchEvent(new window.Event('change',{bubbles:true}));});
 } else {
  localStorage.token='replacement-synthetic';
  if(change==='account-event') await act(async()=>window.dispatchEvent(new window.StorageEvent('storage',{key:'token'})));
 }
 await act(async()=>new Promise(resolve=>setTimeout(resolve,1600)));
 assert.equal(recordsCount(requests),before+(change==='company'?1:0),'only new company initial read is allowed');
 if(change!=='company') {
  assert.match(document.querySelector('.workspace-sync-line').textContent,/Session changed/);
  assert.doesNotMatch(document.querySelector('.workspace-sync-line').textContent,/Last loaded/);
  await click('Refresh');assert.equal(recordsCount(requests),before,'manual cannot dispatch captured old workspace with new token');
 }
}));

test('queued refresh never dispatches while an uncertain financial command is pending',async()=>workspace('owner',async({click,state,requests,posts})=>{
 const item={id:'pos-item',kind:'item',name:'POS item',data:{sale_rate:'100',gst_rate:'0'}};
 state.records=()=>recordsResponse([item]);await click('Refresh');
 await click('POS');await act(async()=>document.querySelector('.pos-product').click());
 await act(async()=>new Promise(resolve=>setTimeout(resolve,250)));
 state.post=()=>{throw TypeError('Synthetic uncertain save');};
 await click('Complete sale');assert.equal(posts.length,1);
 const before=recordsCount(requests);
 await focus();await click('Refresh');
 assert.equal(recordsCount(requests),before);assert.equal(posts.length,1,'catch-up never submits financial writes');
 assert.match(document.querySelector('.workspace-sync-line').textContent,/Refresh pending/);
 assert.match(document.querySelector('.workspace-sync-line').textContent,/finish the pending save/);
 // A retry remains owned by its existing posting hook, never by refresh.
 state.post=()=>recordsResponse({id:'pos-saved',kind:'pos',posted:true,number:'POS-1',amount:'100'});
 await click('Complete sale');assert.equal(posts.length,2);
 await click('Refresh');assert.ok(recordsCount(requests)>before);
}));

test('deferred focus preserves entered payment data until deliberate discard, then reads once',async()=>workspace('owner',async({click,state,invoice,requests,posts,dom})=>{
 await click('Sales invoices');await click('Collect payment');
 const amount=document.querySelector('input[name="amount"]');
 await act(async()=>{Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(amount,'25');amount.dispatchEvent(new window.Event('input',{bubbles:true}));});
 const before=recordsCount(requests);
 state.records=()=>recordsResponse([{...invoice,outstanding:'0'}]);
 await focus();assert.equal(amount.value,'25');assert.equal(recordsCount(requests),before);
 await click('Cancel');assert.match(document.body.textContent,/Discard unsaved changes/);
 assert.equal(recordsCount(requests),before);assert.equal(amount.value,'25');
 await click('Discard draft');assert.equal(recordsCount(requests),before+1);
 assert.equal(posts.length,0,'cancel and catch-up never send payment');
}));

test('hidden trailing timer waits for a visible event without background reads',async()=>workspace('owner',async({click,requests})=>{
 await click('Sales invoices');await focus();const before=recordsCount(requests);
 await focus();Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});
 await act(async()=>new Promise(resolve=>setTimeout(resolve,1600)));
 assert.equal(recordsCount(requests),before);
 Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});
 await act(async()=>document.dispatchEvent(new window.Event('visibilitychange')));
 assert.equal(recordsCount(requests),before+1);
}));

test('dashboard remount labels independently new reports versus previous history snapshot',async()=>workspace('owner',async({click,state,requests})=>{
 await click('Sales invoices');const beforeRecords=recordsCount(requests),beforeSummaries=summariesCount(requests);
 state.summary={sales:'200',receivables:'140',payables:'0'};
 await click('Dashboard');
 assert.equal(recordsCount(requests),beforeRecords);assert.equal(summariesCount(requests),beforeSummaries+1);
 assert.match(document.querySelector('.overview-metric').textContent,/200/);
 assert.match(document.querySelector('.collection-numbers').textContent,/40/);
 const caption=document.querySelector('.dashboard-history-caption').textContent;
 assert.match(caption,/Summary reports refresh independently/);
 assert.match(caption,/invoice collections.*company-history snapshot loaded/);
 assert.match(caption,/Refresh to check for newer records/);
}));
