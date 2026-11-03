import { CORE_ENHANCEMENTS } from '../src/capabilities.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import { act } from 'react';

async function workspace(role, verify, additional = [], capabilities = CORE_ENHANCEMENTS, { masterError = null } = {}) {
  const temporary = await mkdtemp(resolve('node_modules/.workspace-tests-'));
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, MutationObserver: dom.window.MutationObserver, requestAnimationFrame: cb => setTimeout(cb, 0), ResizeObserver: class { observe() {} disconnect() {} }, IS_REACT_ACT_ENVIRONMENT: true });
  window.scrollTo = () => {};
  localStorage.token = 'synthetic-token';
  const company = { id: 'company', name: 'Synthetic company', state_code: '27', tax_mode: 'unregistered', role };
  const invoice = { id: 'invoice', kind: 'sales_invoice', name: 'Synthetic customer', number: 'INV-1', date: '2026-11-02', posted: true, amount: '100', outstanding: '40', data: { lines: [{ description: 'Service', quantity: '1', rate: '100', gst_rate: '0' }], place_of_supply: '27' } };
  const posts = [], requests = [], masterWrites = []; const state = {};
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async (path, options = {}) => {
    requests.push({path,options});
    let data;
    if (path === '/api/capabilities') {
      const advertised = typeof capabilities === 'function' ? capabilities() : capabilities;
      if (advertised === null || advertised?.status) return { ok: false, status: advertised?.status || 404, json: async () => ({ detail: 'Synthetic capability check unavailable' }) };
      data = { api_version: 'synthetic', capabilities_version: 1, supported_features: advertised };
    }
    else if (path === '/api/companies') data = [company, { ...company, id: 'other-company', name: 'Other company' }];
    else if (path.includes('/records?')) data = [invoice, ...additional];
    else if (path.endsWith('/records/invoice')) { const { outstanding, ...detail } = invoice; data = detail; }
    else if (additional.some(row => path.endsWith('/records/' + row.id))) data = additional.find(row => path.endsWith('/records/' + row.id));
    else if (path.includes('/masters/') && options.method === 'PUT') {
      masterWrites.push(JSON.parse(options.body));
      if (state.masterResponse) return state.masterResponse(path, options);
      if (masterError) return { ok: false, status: 409, json: async () => ({ detail: masterError }) };
      data = { id: 'master-saved' };
    }
    else if (path.endsWith('/records') && options.method === 'POST') { posts.push(JSON.parse(options.body)); data = { id: 'saved' }; }
    else if (path.endsWith('/bank-accounts')) data = [{ id: 'default', name: 'Synthetic bank' }];
    else if (path.endsWith('/preferences')) data = { document_template: 'classic' };
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


for(const action of ['edit','archive','reactivate']) test(`mounted master ${action} blocks replacement session and recovers under original session`,async()=>{
 const master={id:'original-master',kind:'item',name:'Shared item',data:{version:7,sale_rate:'100',purchase_rate:'60',is_active:action!=='reactivate'}};
 await workspace('owner',async({click,dom,requests,masterWrites})=>{
  await click('Items');await click('Edit');
  if(action==='edit') {
   const input=document.querySelector('input[name="sale_rate"]');
   await act(async()=>{Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(input,'125');input.dispatchEvent(new dom.window.Event('input',{bubbles:true}));});
  } else {
   const active=[...document.querySelectorAll('.modal label')].find(l=>l.textContent.includes('Active for new transactions')).querySelector('input');
   await act(async()=>active.click());
  }
  // Ordinary cross-tab localStorage replacement, before its storage event reaches this tab.
  localStorage.token='replacement-synthetic-account';
  await act(async()=>document.querySelector('.modal form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));
  assert.equal(requests.some(r=>r.path.includes('/masters/')&&r.options.method==='PUT'),false,'changed actor cannot submit original intent');
  assert.match(document.querySelector('.modal').textContent,/signed-in session changed/);
  if(action==='edit') assert.equal(document.querySelector('input[name="sale_rate"]').value,'125');
  localStorage.token='synthetic-token';
  await act(async()=>document.querySelector('.modal form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));
  const mutation=requests.find(r=>r.path.includes('/masters/')&&r.options.method==='PUT');
  assert.ok(mutation,'exact original session permits deliberate save');
  assert.equal(mutation.options.headers.Authorization,'Bearer synthetic-token');
  assert.equal(masterWrites.length,1);
  assert.equal(masterWrites[0].version,7,'original revision is preserved');
  assert.equal(masterWrites[0].is_active,action==='archive'?false:true);
  if(action==='edit') assert.equal(masterWrites[0].sale_rate,'125');
 },[master]);
});

test('control: mounted document draft edit already blocks replacement-session dispatch',async()=>{
 const draft={id:'draft',kind:'estimate',name:'Draft customer',number:'EST-1',date:'2026-11-03',amount:'100',posted:false,data:{version:4,lines:[{description:'Original service',quantity:'1',rate:'100',gst_rate:'0'}]}};
 await workspace('owner',async({click,dom,requests})=>{
  await click('Estimates');await click('Edit');
  localStorage.token='replacement-synthetic-account';
  await act(async()=>document.querySelector('.modal form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));
  assert.equal(requests.some(r=>r.options.method==='PUT'),false);
  assert.match(document.querySelector('.modal').textContent,/signed-in session changed/);
  assert.ok(document.querySelector('.modal form'),'original form remains mounted');
  await act(async()=>new Promise(resolve=>setTimeout(resolve,300)));
 },[draft]);
});

test('control: late master error cannot log out replacement session; original CAS conflict preserves entered input',async()=>{
 const master={id:'late-master',kind:'item',name:'Shared item',data:{version:7,sale_rate:'100',purchase_rate:'60',is_active:true}};
 await workspace('owner',async({click,dom,requests,masterWrites,state})=>{
  await click('Items');await click('Edit');
  const input=document.querySelector('input[name="sale_rate"]');
  await act(async()=>{Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(input,'125');input.dispatchEvent(new dom.window.Event('input',{bubbles:true}));});
  let finish;state.masterResponse=()=>new Promise(resolve=>{finish=()=>resolve({ok:false,status:401,json:async()=>({detail:'Old session expired'})});});
  await act(async()=>document.querySelector('.modal form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));
  const picker=document.querySelector('[aria-label="Choose company"]');
  await act(async()=>{picker.value='other-company';picker.dispatchEvent(new dom.window.Event('change',{bubbles:true}));});
  assert.equal(picker.value,'company','normal company switch is blocked by open modal');
  localStorage.token='replacement-synthetic-account';
  await act(async()=>finish());
  assert.equal(localStorage.token,'replacement-synthetic-account');
  assert.ok(document.querySelector('.modal form'));
  assert.equal(document.querySelector('input[name="sale_rate"]').value,'125');
  assert.match(document.querySelector('.modal').textContent,/response was not applied/);
  localStorage.token='synthetic-token';
  state.masterResponse=()=>({ok:false,status:409,json:async()=>({detail:'This party or item changed on another device. Close this editor, refresh company data and reopen it before saving.'})});
  await act(async()=>document.querySelector('.modal form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));
  assert.deepEqual(masterWrites[1],masterWrites[0]);assert.equal(masterWrites[1].version,7);
  assert.equal(document.querySelector('input[name="sale_rate"]').value,'125');
  assert.match(document.querySelector('.modal').textContent,/changed on another device/);
  assert.equal(requests.filter(r=>r.options.method==='PUT').length,2);
 },[master]);
});
