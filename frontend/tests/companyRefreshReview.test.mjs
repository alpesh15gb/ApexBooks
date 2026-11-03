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
  window.scrollTo = () => {}; window.HTMLElement.prototype.scrollIntoView = () => {};
  localStorage.token = 'synthetic-token';
  const company = { id: 'company', name: 'Synthetic company', state_code: '27', tax_mode: 'unregistered', role };
  const invoice = { id: 'invoice', kind: 'sales_invoice', name: 'Synthetic customer', number: 'INV-1', date: '2026-11-02', posted: true, amount: '100', outstanding: '40', data: { lines: [{ description: 'Service', quantity: '1', rate: '100', gst_rate: '0' }], place_of_supply: '27' } };
  const posts = [], requests = [], masterWrites = []; const state = { records: null, preferences: null };
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
    else if (path.endsWith('/records') && options.method === 'POST') { posts.push(JSON.parse(options.body)); data = { id: 'saved' }; }
    else if (path.endsWith('/bank-accounts')) data = [{ id: 'default', name: 'Synthetic bank' }];
    else if (path.endsWith('/preferences')) { if(state.preferences) return state.preferences(path, options); data = { document_template: 'vintage' }; }
    else if (path.includes('/reports/summary')) data = {sales:'1000',receivables:'500',payables:'300'};
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


test('company layout remains unavailable until current company read succeeds', async () => workspace('owner', async ({click, state, posts}) => {
 await click('Settings');
 const tab = [...document.querySelectorAll('button')].find(b => b.textContent.includes('Documents & branding'));
 await act(async () => tab.click());
 const layout = () => [...document.querySelectorAll('label')].find(l => l.textContent.includes('Document PDF layout')).querySelector('select');
 assert.equal(layout().value, 'vintage');
 let finish;
 state.preferences = () => new Promise(resolve => { finish = () => resolve({ok:false,status:503,json:async()=>({detail:'Other company preferences unavailable'})}); });
 const picker=document.querySelector('[aria-label="Choose company"]');
 await act(async()=>{picker.value='other-company';picker.dispatchEvent(new window.Event('change',{bubbles:true}));});
 assert.equal(picker.value,'other-company');
 await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Documents & branding')).click());
 assert.equal(layout().value,'');
 assert.equal(layout().disabled,true);
 await act(async()=>finish());
 assert.match(document.body.textContent,/service is temporarily unavailable/);
 assert.equal(layout().value,'');
 assert.equal(layout().disabled,true);
 state.preferences=()=>({ok:true,json:async()=>({document_template:'modern'})});
 await click('Retry document layout');
 assert.equal(layout().value,'modern'); assert.equal(layout().disabled,false);
 assert.equal(posts.length,0);
}));

test('review: second-page failure preserves last good records and late old-company response is ignored', async () => workspace('owner', async ({click,state,invoice})=>{
 await click('Sales invoices');
 assert.match(document.querySelector('.register').textContent,/Synthetic customer/);
 let finish;
 state.records = path => new URL(path,'http://localhost').searchParams.get('offset')==='0'
  ? {ok:true,json:async()=>Array.from({length:500},(_,i)=>({...invoice,id:'partial-'+i,name:'Unconfirmed partial'}))}
  : new Promise(resolve=>{finish=()=>resolve({ok:false,status:503,json:async()=>({detail:'Second page interrupted'})});});
 await click('Refresh');
 assert.equal(typeof finish,'function');
 assert.match(document.querySelector('.register').textContent,/Synthetic customer/);
 assert.doesNotMatch(document.querySelector('.register').textContent,/Unconfirmed partial/);
 await act(async()=>finish());
 assert.match(document.querySelector('.register').textContent,/Synthetic customer/);
 assert.match(document.body.textContent,/Refresh needed/);
 state.records=()=>new Promise(resolve=>{finish=()=>resolve({ok:true,json:async()=>[{...invoice,id:'late',name:'Obsolete customer'}]});});
 await click('Refresh');const old=finish;
 state.records=()=>({ok:true,json:async()=>[{...invoice,id:'new',name:'Other company customer'}]});
 const picker=document.querySelector('[aria-label="Choose company"]');
 await act(async()=>{picker.value='other-company';picker.dispatchEvent(new window.Event('change',{bubbles:true}));});
 await act(async()=>old());
 assert.match(document.querySelector('.register').textContent,/Other company customer/);
 assert.doesNotMatch(document.querySelector('.register').textContent,/Obsolete customer|Synthetic customer/);
}));

test('failed initial history with successful summaries does not assert zero or first invoice', async () => workspace('owner', async () => {
 assert.match(document.body.textContent,/Refresh needed/);
 assert.match(document.querySelector('.attention-strip').textContent,/— unpaid bills/);
 assert.match(document.querySelector('.attention-strip').textContent,/— open estimates/);
 assert.equal(document.querySelector('.collection-ring strong').textContent,'—');
 assert.doesNotMatch(document.querySelector('.activity-insight').textContent,/Your books start here/);
 assert.doesNotMatch(document.querySelector('.activity-insight').textContent,/Create your first invoice/);
 assert.match(document.querySelector('.overview-metric').textContent,/1,000/);
}, [], CORE_ENHANCEMENTS, {recordsUnavailable:true}));

test('review: focus refresh wins over older in-flight manual refresh in same company', async () => workspace('owner', async ({click,state,invoice})=>{
 await click('Sales invoices');
 let finish;
 state.records=()=>new Promise(resolve=>{finish=()=>resolve({ok:true,json:async()=>[{...invoice,id:'old',name:'Obsolete overlap'}]});});
 await click('Refresh');
 assert.equal(typeof finish,'function');
 state.records=()=>({ok:true,json:async()=>[{...invoice,id:'new',name:'Latest overlap'}]});
 Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'});
 await act(async()=>window.dispatchEvent(new window.Event('focus')));
 assert.match(document.querySelector('.register').textContent,/Latest overlap/);
 await act(async()=>finish());
 assert.match(document.querySelector('.register').textContent,/Latest overlap/);
 assert.doesNotMatch(document.querySelector('.register').textContent,/Obsolete overlap/);
}));

test('malformed successful refresh preserves last confirmed company register', async () => workspace('owner', async ({click,state})=>{
 await click('Sales invoices');
 assert.match(document.querySelector('.register').textContent,/Synthetic customer/);
 state.records=()=>({ok:true,json:async()=>[{name:'Invalid missing identity'}]});
 await click('Refresh');
 assert.match(document.querySelector('.register').textContent,/Synthetic customer/);
 assert.match(document.body.textContent,/Invalid company records response/);
 assert.match(document.body.textContent,/Refresh needed/);
 assert.doesNotMatch(document.querySelector('.register').textContent,/Invalid missing identity/);
}));

test('confirmed empty history still shows honest zero and first invoice guidance', async () => workspace('owner', async () => {
 assert.match(document.querySelector('.attention-strip').textContent,/0 unpaid bills/);
 assert.equal(document.querySelector('.collection-ring strong').textContent,'0%');
 assert.match(document.querySelector('.activity-insight').textContent,/Your books start here/);
}, [], CORE_ENHANCEMENTS, {recordsUnavailable:'empty'}));

test('preference account change blocks missed-event writes and stale completion; explicit read recovers', async () => workspace('owner', async ({click,state})=>{
 await click('Settings'); await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Documents & branding')).click());
 const layout=()=>document.querySelector('.document-layout-preference select');
 const choose=async value=>act(async()=>{layout().value=value;layout().dispatchEvent(new window.Event('change',{bubbles:true}));});
 let writes=0, finish;
 state.preferences=(path,options)=>{if(options.method==='PUT'){writes++;return new Promise(resolve=>{finish=()=>resolve({ok:true,json:async()=>({document_template:'modern'})});});}return {ok:true,json:async()=>({document_template:'elegant'})};};
 localStorage.token='replacement-synthetic';
 await choose('modern'); assert.equal(writes,0,'missed storage event still blocks dispatch');
 await act(async()=>window.dispatchEvent(new window.StorageEvent('storage',{key:'token'})));
 assert.equal(layout().disabled,true);assert.equal(layout().value,'');
 await click('Retry document layout');assert.equal(layout().value,'elegant');
 await choose('modern');assert.equal(writes,1);assert.equal(layout().disabled,true);
 localStorage.token='another-synthetic';
 await act(async()=>window.dispatchEvent(new window.StorageEvent('storage',{key:'token'})));
 await act(async()=>finish());
 assert.equal(layout().value,'');assert.equal(layout().disabled,true);
 await click('Retry document layout');assert.equal(layout().value,'elegant');assert.equal(layout().disabled,false);
 assert.equal(writes,1,'reads and recovery never autosave');
}));

for (const operation of ['GET', 'PUT']) test(`late preference ${operation} from previous company cannot overwrite or disable current setting`, async () => workspace('owner', async ({click,state})=>{
 const docs=async()=>act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Documents & branding')).click());
 const layout=()=>document.querySelector('.document-layout-preference select');
 let finish, writes=0;
 if(operation==='GET') state.preferences=()=>new Promise(resolve=>{finish=()=>resolve({ok:true,json:async()=>({document_template:'vintage'})});});
 await click('Settings'); await docs();
 if(operation==='PUT') {
  state.preferences=(path,options)=>{if(options.method==='PUT'){writes++;return new Promise(resolve=>{finish=()=>resolve({ok:false,status:503,json:async()=>({detail:'Old company save failed'})});});}return {ok:true,json:async()=>({document_template:'modern'})};};
  await act(async()=>{layout().value='modern';layout().dispatchEvent(new window.Event('change',{bubbles:true}));});
  assert.equal(layout().disabled,true);
 }
 assert.equal(typeof finish,'function');const old=finish;
 state.preferences=()=>({ok:true,json:async()=>({document_template:'elegant'})});
 const picker=document.querySelector('[aria-label="Choose company"]');
 await act(async()=>{picker.value='other-company';picker.dispatchEvent(new window.Event('change',{bubbles:true}));});await docs();
 assert.equal(layout().value,'elegant');assert.equal(layout().disabled,false);
 await act(async()=>old());
 assert.equal(layout().value,'elegant');assert.equal(layout().disabled,false);
 assert.equal(document.querySelector('.document-layout-preference [role="alert"]'),null);
 assert.equal(writes,operation==='PUT'?1:0);
}));

test('returning to original token after an obsolete preference read keeps explicit recovery available', async () => workspace('owner', async ({click,state})=>{
 let finish;
 state.preferences=()=>new Promise(resolve=>{finish=()=>resolve({ok:true,json:async()=>({document_template:'vintage'})});});
 await click('Settings');await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Documents & branding')).click());
 localStorage.token='other-session';
 await act(async()=>finish()); // Deliberately no storage event before the response.
 localStorage.token='synthetic-token';
 await act(async()=>window.dispatchEvent(new window.StorageEvent('storage',{key:'token'})));
 state.preferences=()=>({ok:true,json:async()=>({document_template:'modern'})});
 await click('Retry document layout');
 assert.equal(document.querySelector('.document-layout-preference select').value,'modern');
 assert.equal(document.querySelector('.document-layout-preference select').disabled,false);
}));

for(const failure of ['network','500']) test(`ambiguous preference PUT ${failure} requires read reconciliation without another write`, async()=>workspace('owner',async({click,state})=>{
 await click('Settings');await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Documents & branding')).click());
 const layout=()=>document.querySelector('.document-layout-preference select');
 let stored='vintage', writes=0;
 state.preferences=(path,options)=>{
  if(options.method==='PUT') {writes++;stored=JSON.parse(options.body).document_template;if(failure==='network') throw TypeError('Synthetic connection lost');return {ok:false,status:500,json:async()=>({detail:'Synthetic response failed after commit'})};}
  return {ok:true,json:async()=>({document_template:stored})};
 };
 await act(async()=>{layout().value='modern';layout().dispatchEvent(new window.Event('change',{bubbles:true}));});
 assert.equal(stored,'modern','synthetic server committed requested preference');
 assert.equal(layout().disabled,true,'uncertain result cannot leave selector ready');
 assert.equal(layout().value,'','previous value is no longer confirmed');
 await click('Retry document layout');
 assert.equal(layout().value,'modern');assert.equal(layout().disabled,false);
 assert.equal(writes,1,'reconciliation is GET only');
}));
