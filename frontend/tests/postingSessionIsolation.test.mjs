import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import { act } from 'react';
for (const interrupted of [true, false]) test(`${interrupted ? 'Uncertain retry' : 'First save from a stale form'} cannot run under another session`,async()=>{
 const temp=await mkdtemp(resolve('node_modules/.posting-navigation-'));
 const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/'});
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,MutationObserver:dom.window.MutationObserver,requestAnimationFrame:callback=>setTimeout(callback,0),ResizeObserver:class{observe(){}disconnect(){}},IS_REACT_ACT_ENVIRONMENT:true});
 window.scrollTo=()=>{};localStorage.token='synthetic-token';
 const previousFetch=globalThis.fetch, submissions=[];
 let roleDenied=false;
 const company={id:'c1',name:'Synthetic company',state_code:'27',tax_mode:'unregistered',role:'owner'};
 globalThis.fetch=async(path,options={})=>{
  let data;
  if(path==='/api/companies')data=[company,{...company,id:'c2',name:'Other company'}];
  else if(path.includes('/records?'))data=[{id:'item',kind:'item',name:'Synthetic item',date:'2026-11-02',data:{sale_rate:'100',gst_rate:'0'}}];
  else if(path.endsWith('/documents/preview'))data={amount:'100',data:{cgst:'0',sgst:'0',igst:'0'}};
  else if(path.endsWith('/records')&&options.method==='POST'){
   submissions.push(options);
   if(interrupted&&submissions.length===1)throw new TypeError('Synthetic response lost');
   if(roleDenied)return{ok:false,status:403,json:async()=>({detail:'Write access required'})};
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
  await click('POS');await act(async()=>document.querySelector('.pos-product').click());
  await act(async()=>new Promise(resolve=>setTimeout(resolve,250)));
  if(interrupted) {
    await click('Complete sale');assert.equal(submissions.length,1);
    assert.match(document.body.textContent,/previous response was not confirmed/);
  }
  const sentBeforeChange=submissions.length;
  const originalForm=document.querySelector('.pos-grid form');
  localStorage.token='different-synthetic-account-token';
  await act(async()=>window.dispatchEvent(new window.StorageEvent('storage',{key:'token',oldValue:'synthetic-token',newValue:'different-synthetic-account-token',storageArea:localStorage})));
  await click('Complete sale');
  assert.equal(submissions.length,sentBeforeChange,'Changed actor must not send a financial request');
  assert.match(document.body.textContent,/signed-in session changed/);
  // A fresh login token is not identity proof, and no storage event is needed.
  localStorage.token='fresh-login-synthetic-token';
  await click('Complete sale');assert.equal(submissions.length,sentBeforeChange);
  localStorage.removeItem('token');
  await click('Complete sale');assert.equal(submissions.length,sentBeforeChange);
  assert.equal(document.querySelector('.pos-grid form'),originalForm);
  if(interrupted) {
    const companyPicker=document.querySelector('[aria-label="Choose company"]');
    await act(async()=>{companyPicker.value='c2';companyPicker.dispatchEvent(new window.Event('change',{bubbles:true}));});
    assert.equal(companyPicker.value,'c1');
    assert.equal(document.querySelector('.pos-grid form'),originalForm);
    localStorage.token='synthetic-token';
    roleDenied=true;
    await click('Complete sale');assert.equal(submissions.length,2);
    assert.match(document.body.textContent,/Write access required/);
    const stillPending=new window.Event('beforeunload',{cancelable:true});window.dispatchEvent(stillPending);assert.equal(stillPending.defaultPrevented,true);
    await click('Sign out');assert.equal(localStorage.token,'synthetic-token');
    roleDenied=false;
  }
  localStorage.token='synthetic-token';
  await click('Complete sale');
  assert.equal(submissions.length,interrupted?3:1);
  for(const request of submissions)assert.deepEqual(request,submissions[0],'Recovery must retain the exact body, key and original authorization');
  assert.match(document.querySelector('.pos-receipt').textContent,/Sale completed/);
  const recoveredUnload=new window.Event('beforeunload',{cancelable:true});window.dispatchEvent(recoveredUnload);assert.equal(recoveredUnload.defaultPrevented,false);
 }finally{globalThis.fetch=previousFetch;dom.window.close();await rm(temp,{recursive:true,force:true});}
});
