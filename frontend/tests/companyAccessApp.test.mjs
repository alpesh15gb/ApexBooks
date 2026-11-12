import test from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,rm} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';import {build} from 'esbuild';import {JSDOM} from 'jsdom';import {act} from 'react';
for(const restoredRole of ['editor','viewer'])test(`actual App preserves master draft through access recovery as ${restoredRole}`,async()=>{
 const temp=await mkdtemp(resolve('node_modules/.company-access-'));const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/#/party'});
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,MutationObserver:dom.window.MutationObserver,requestAnimationFrame:cb=>setTimeout(cb,0),ResizeObserver:class{observe(){}disconnect(){}},IS_REACT_ACT_ENVIRONMENT:true});window.scrollTo=()=>{};localStorage.token='synthetic';localStorage.companyId='c1';
 let revoked=false,posts=0,role='editor';globalThis.fetch=async(path,options={})=>{
  const value=(status,data)=>({status,ok:status<400,json:async()=>data});
  if(path==='/api/companies')return value(200,revoked?[]:[{id:'c1',name:'Synthetic company',role,tax_mode:'unregistered'}]);
  if(path.includes('/records')&&options.method==='POST'){posts++;return value(404,{detail:'Company not found'});}
  if(path.includes('/records?')||path.endsWith('/bank-accounts'))return value(revoked?404:200,revoked?{detail:'Company not found'}:[]);
  if(path.endsWith('/preferences'))return value(200,{});return value(503,{detail:'Synthetic optional metadata unavailable'});
 };
 try{
  const file=resolve(temp,'app.mjs');await build({entryPoints:['src/main.jsx'],outfile:file,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react','react-dom','react-dom/client','lucide-react'],loader:{'.css':'empty'}});await act(async()=>{await import(pathToFileURL(file));});
  const button=[...document.querySelectorAll('button')].find(b=>/Add party|New party/i.test(b.textContent));assert.ok(button,[...document.querySelectorAll('button')].map(b=>b.textContent).join('|'));
  await act(async()=>button.click());const input=document.querySelector('.overlay input');assert.ok(input);
  await act(async()=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(input,'Preserved synthetic draft');input.dispatchEvent(new window.Event('input',{bubbles:true}));});
  revoked=true;const form=input.closest('form');assert.ok(form);await act(async()=>form.dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
  assert.equal(posts,1);assert.match(form.textContent,/Refresh company access before continuing/);assert.ok(document.querySelector('[data-company-locked="true"]').hidden);assert.match(document.body.textContent,/Company access removed or unavailable/);assert.equal(input.value,'Preserved synthetic draft');
  revoked=false;role=restoredRole;await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Refresh company access').click());
  assert.equal(document.querySelector('[data-company-locked]').hidden,false);assert.equal(input.value,'Preserved synthetic draft');assert.equal(input.isConnected,true);assert.doesNotMatch(form.textContent,/Refresh company access before continuing/);assert.equal(posts,1);assert.equal(input.closest('[inert]'),null);assert.equal([...document.querySelectorAll('button')].find(b=>b.textContent==='Save party').disabled,restoredRole==='viewer');
 }finally{dom.window.close();await rm(temp,{recursive:true,force:true});}
});
