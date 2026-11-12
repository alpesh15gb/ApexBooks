import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';
import {build} from 'esbuild';import {JSDOM} from 'jsdom';import {act} from 'react';
for(const race of ['before-click','pending','current'])test(`logout owns accepted session: ${race}`,async()=>{
 const temp=await mkdtemp(resolve('node_modules/.logout-'));const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/'});
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,MutationObserver:dom.window.MutationObserver,requestAnimationFrame:cb=>setTimeout(cb,0),ResizeObserver:class{observe(){}disconnect(){}},IS_REACT_ACT_ENVIRONMENT:true});window.scrollTo=()=>{};localStorage.token='synthetic-old';localStorage.companyId='c1';
 const oldFetch=globalThis.fetch;let finish;let calls=0;const pending=new Promise(r=>finish=r);
 globalThis.fetch=async path=>{
  if(path==='/api/auth/logout'){calls++;return pending;}
  if(path==='/api/companies')return{ok:true,json:async()=>[{id:'c1',name:'Synthetic',role:'owner',tax_mode:'unregistered'}]};
  if(path.includes('/records?')||path.endsWith('/bank-accounts'))return{ok:true,json:async()=>[]};
  if(path.endsWith('/preferences'))return{ok:true,json:async()=>({})};
  return{ok:false,status:503,json:async()=>({detail:'Synthetic optional metadata unavailable'})};
 };
 try{
  const outfile=resolve(temp,'app.mjs');await build({entryPoints:['src/main.jsx'],outfile,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react','react-dom','react-dom/client','lucide-react'],loader:{'.css':'empty'}});
  await act(async()=>{await import(pathToFileURL(outfile));});
  const button=[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Sign out'));assert.ok(button);
  if(race==='before-click')localStorage.token='synthetic-new';
  await act(async()=>{button.click();});assert.equal(calls,race==='before-click'?0:1);
  if(race==='pending')localStorage.token='synthetic-new';
  await act(async()=>{finish({ok:true,status:200,json:async()=>({})});});
  assert.equal(localStorage.getItem('token'),race==='current'?null:'synthetic-new');assert.equal(localStorage.getItem('companyId'),race==='current'?null:'c1');
  if(race==='before-click')assert.match(document.body.textContent,/Your sign-in changed in another tab/);
 }finally{globalThis.fetch=oldFetch;dom.window.close();await rm(temp,{recursive:true,force:true});}
});
