import test from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,rm} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';import {build} from 'esbuild';import {JSDOM} from 'jsdom';import {act} from 'react';
for(const kind of ['opening','adjustments']) for(const restoredRole of ['editor','viewer'])test(`actual App preserves ${kind} stock draft through access recovery as ${restoredRole}`,async()=>{
 const temp=await mkdtemp(resolve('node_modules/.company-access-'));const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/#/item'});
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,MutationObserver:dom.window.MutationObserver,requestAnimationFrame:cb=>setTimeout(cb,0),ResizeObserver:class{observe(){}disconnect(){}},IS_REACT_ACT_ENVIRONMENT:true});window.scrollTo=()=>{};localStorage.token='synthetic';localStorage.companyId='c1';
 let revoked=false,posts=0,role='editor';globalThis.fetch=async(path,options={})=>{
  const value=(status,data)=>({status,ok:status<400,json:async()=>data});
  if(path==='/api/companies')return value(200,revoked?[]:[{id:'c1',name:'Synthetic company',role,tax_mode:'unregistered'}]);
  if(path.includes('/stock/')&&options.method==='POST'){posts++;return value(200,{});}
  if(path.includes('/records?')||path.endsWith('/bank-accounts'))return value(revoked?404:200,revoked?{detail:'Company not found'}:path.includes('/records?')?[{id:'item1',kind:'item',name:'Synthetic item',data:{track_stock:true,unit:'pcs'}}]:[]);
  if(path.endsWith('/preferences'))return value(200,{});return value(503,{detail:'Synthetic optional metadata unavailable'});
 };
 try{
  const file=resolve(temp,'app.mjs');await build({entryPoints:['src/main.jsx'],outfile:file,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react','react-dom','react-dom/client','lucide-react'],loader:{'.css':'empty'}});await act(async()=>{await import(pathToFileURL(file));});
  const button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===(kind==='opening'?'Opening stock':'Adjust stock'));assert.ok(button,[...document.querySelectorAll('button')].map(b=>b.textContent).join('|'));
  await act(async()=>button.click());const input=document.querySelector('.overlay input[name=quantity]');assert.ok(input);
  await act(async()=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(input,'5');input.dispatchEvent(new window.Event('input',{bubbles:true}));});
  const form=input.closest('form');assert.ok(form);const extra=form.querySelector(kind==='opening'?'[name=unit_cost]':'[name=reason]');await act(async()=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(extra,kind==='opening'?'80':'Synthetic count');extra.dispatchEvent(new window.Event('input',{bubbles:true}));});revoked=true;await act(async()=>document.querySelector('.workspace-sync-line button').click());
  assert.equal(posts,0);assert.ok(document.querySelector('[data-company-locked="true"]').hidden);assert.match(document.body.textContent,/Company access removed or unavailable/);assert.equal(input.value,'5');
  revoked=false;role=restoredRole;await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Refresh company access').click());
  assert.equal(document.querySelector('[data-company-locked]').hidden,false);assert.equal(input.value,'5');assert.equal(input.isConnected,true);assert.equal(posts,0);assert.equal(input.closest('[inert]'),null);assert.equal([...document.querySelectorAll('button')].find(b=>b.textContent===(kind==='opening'?'Post opening stock':'Post adjustment')).disabled,restoredRole==='viewer');
  assert.equal(form.querySelector('fieldset').disabled,restoredRole==='viewer');
  await act(async()=>form.dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
  assert.equal(posts,restoredRole==='viewer'?0:1);
  if(restoredRole==='viewer'){assert.match(form.textContent,/Read-only access/);assert.equal(input.value,'5');assert.equal(form.querySelector('button[type=button]').disabled,false);}else assert.equal(form.isConnected,false);
 }finally{dom.window.close();await rm(temp,{recursive:true,force:true});}
});
