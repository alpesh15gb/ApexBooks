import test from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,rm} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';import {build} from 'esbuild';import {JSDOM} from 'jsdom';import {act} from 'react';
test('actual App clears open viewer detail on revoked refresh and does not resurrect it',async()=>{
 const temp=await mkdtemp(resolve('node_modules/.company-access-'));const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/#/sales_invoice'});
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,MutationObserver:dom.window.MutationObserver,requestAnimationFrame:cb=>setTimeout(cb,0),ResizeObserver:class{observe(){}disconnect(){}},IS_REACT_ACT_ENVIRONMENT:true});window.scrollTo=()=>{};localStorage.token='synthetic';localStorage.companyId='c1';
 const record={id:'r1',kind:'sales_invoice',name:'Synthetic buyer',number:'INV-SYN',date:'2026-04-02',amount:'100',posted:true,outstanding:'100',data:{lines:[{description:'Synthetic line',quantity:1,rate:100}]}};let revoked=false,posts=0;globalThis.fetch=async(path,options={})=>{
  const value=(status,data)=>({status,ok:status<400,json:async()=>data});
  if(path==='/api/companies')return value(200,revoked?[]:[{id:'c1',name:'Synthetic company',role:'viewer',tax_mode:'unregistered'}]);
  if(path.includes('/records')&&options.method==='POST'){posts++;return value(404,{detail:'Company not found'});}
  if(path.endsWith('/records/r1'))return value(200,record);
  if(path.includes('/records?')||path.endsWith('/bank-accounts'))return value(revoked?404:200,revoked?{detail:'Company not found'}:(path.includes('/records?')?[record]:[]));
  if(path.endsWith('/preferences'))return value(200,{});return value(503,{detail:'Synthetic optional metadata unavailable'});
 };
 try{
  const file=resolve(temp,'app.mjs');await build({entryPoints:['src/main.jsx'],outfile:file,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react','react-dom','react-dom/client','lucide-react'],loader:{'.css':'empty'}});await act(async()=>{await import(pathToFileURL(file));});
  const button=[...document.querySelectorAll('button')].find(b=>b.textContent==='INV-SYN');assert.ok(button);
  await act(async()=>button.click());assert.ok(document.querySelector('.transaction-detail'));
  revoked=true;await act(async()=>document.querySelector('.workspace-sync-line button').click());
  assert.equal(document.querySelector('.transaction-detail'),null);assert.ok(document.querySelector('[data-company-locked="true"]').hidden);assert.equal(posts,0);
  revoked=false;await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Refresh company access').click());
  assert.equal(document.querySelector('[data-company-locked]').hidden,false);assert.equal(document.querySelector('.transaction-detail'),null);assert.equal(posts,0);

 }finally{dom.window.close();await rm(temp,{recursive:true,force:true});}
});
