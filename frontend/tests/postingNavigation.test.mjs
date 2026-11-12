import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import { act } from 'react';
test('an uncertain inline POS save survives navigation, company switch, signout and browser back until exact retry recovers',async()=>{
 const temp=await mkdtemp(resolve('node_modules/.posting-navigation-'));
 const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/'});
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,MutationObserver:dom.window.MutationObserver,requestAnimationFrame:callback=>setTimeout(callback,0),ResizeObserver:class{observe(){}disconnect(){}},IS_REACT_ACT_ENVIRONMENT:true});
 window.scrollTo=()=>{};localStorage.token='synthetic-token';
 const previousFetch=globalThis.fetch, submissions=[];
 const company={id:'c1',name:'Synthetic company',state_code:'27',tax_mode:'unregistered',role:'owner'};
 globalThis.fetch=async(path,options={})=>{
  let data;
  if(path==='/api/companies')data=[company,{...company,id:'c2',name:'Other company'}];
  else if(path.includes('/records?'))data=[{id:'item',kind:'item',name:'Synthetic item',date:'2026-11-02',data:{sale_rate:'100',gst_rate:'0'}}];
  else if(path.endsWith('/documents/preview'))data={amount:'100',data:{cgst:'0',sgst:'0',igst:'0'}};
  else if(path.endsWith('/records')&&options.method==='POST'){
   submissions.push(options);
   if(submissions.length===1)throw new TypeError('Synthetic response lost');
   data={id:'saved',number:'POS-1',amount:'100'};
  }else if(path.endsWith('/preferences'))data={document_template:'classic'};
  else if(path.endsWith('/bank-accounts')||path.endsWith('/accounts')||path.endsWith('/journals'))data=[];
  else return{ok:false,status:503,json:async()=>({detail:'Synthetic report unavailable'})};
  return{ok:true,json:async()=>data};
 };
 const click=async text=>{const button=[...document.querySelectorAll('button')].find(button=>button.textContent.trim()===text);assert.ok(button,text);await act(async()=>button.click());};
 try{
  const outfile=resolve(temp,'app.mjs');await build({entryPoints:['src/main.jsx'],outfile,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react','react-dom','react-dom/client','lucide-react'],loader:{'.css':'empty'}});
  await act(async()=>{await import(pathToFileURL(outfile));});
  await click('Sales');await click('POS');await act(async()=>document.querySelector('.pos-product').click());
  await act(async()=>new Promise(resolve=>setTimeout(resolve,250)));
  await click('Complete sale');assert.equal(submissions.length,1);
  assert.match(document.body.textContent,/previous response was not confirmed/);
  const originalForm=document.querySelector('.pos-grid form');
  await click('Items');assert.equal(document.querySelector('.pos-grid form'),originalForm);
  await click('Sign out');assert.equal(localStorage.token,'synthetic-token');
  const select=document.querySelector('[aria-label="Choose company"]');
  await act(async()=>{select.value='c2';select.dispatchEvent(new window.Event('change',{bubbles:true}));});
  assert.equal(select.value,'c1');assert.equal(document.querySelector('.pos-grid form'),originalForm);
  await act(async()=>{window.history.pushState({},'','#/item');window.dispatchEvent(new window.PopStateEvent('popstate'));});
  assert.equal(window.location.hash,'#/pos');assert.equal(document.querySelector('.pos-grid form'),originalForm);
  const unload=new window.Event('beforeunload',{cancelable:true});window.dispatchEvent(unload);assert.equal(unload.defaultPrevented,true);
  await click('Complete sale');assert.equal(submissions.length,2);
  assert.equal(submissions[0].body,submissions[1].body);assert.equal(submissions[0].headers['Idempotency-Key'],submissions[1].headers['Idempotency-Key']);
  const recoveredUnload=new window.Event('beforeunload',{cancelable:true});window.dispatchEvent(recoveredUnload);assert.equal(recoveredUnload.defaultPrevented,false);
  await click('Items');assert.equal(window.location.hash,'#/item');assert.equal(document.querySelector('.pos-grid'),null);
 }finally{globalThis.fetch=previousFetch;dom.window.close();await rm(temp,{recursive:true,force:true});}
});
