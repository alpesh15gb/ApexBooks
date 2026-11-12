import test from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,rm,readFile} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';import {build} from 'esbuild';import {JSDOM} from 'jsdom';import {act} from 'react';
for(const outcome of ['success','failure'])for(const restoredRole of ['current','switch'])test(`actual App restore navigation ${restoredRole}/${outcome}`,async()=>{
 const temp=await mkdtemp(resolve('node_modules/.company-access-'));const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/#/party'});
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,MutationObserver:dom.window.MutationObserver,requestAnimationFrame:cb=>setTimeout(cb,0),ResizeObserver:class{observe(){}disconnect(){}},IS_REACT_ACT_ENVIRONMENT:true});window.scrollTo=()=>{};localStorage.token='synthetic';localStorage.companyId='c1';
 let revoked=false,posts=0,role='editor',delay=false,finish;globalThis.fetch=async(path,options={})=>{
  const value=(status,data)=>({status,ok:status<400,json:async()=>data});
  if(path==='/api/companies'){const rows=[{id:'c1',name:'Synthetic company',role,tax_mode:'unregistered'},{id:'c2',name:'Second',role:'owner'},{id:'restored',name:'Restored',role:'owner'}];return delay?new Promise(r=>finish=()=>r(outcome==='success'?value(200,rows):value(503,{detail:'Synthetic refresh failed'}))):value(200,rows);}
  if(path.includes('/records')&&options.method==='POST'){posts++;return value(404,{detail:'Company not found'});}
  if(path.includes('/records?')||path.endsWith('/bank-accounts'))return value(revoked?404:200,revoked?{detail:'Company not found'}:[]);
  if(path.endsWith('/preferences'))return value(200,{});return value(503,{detail:'Synthetic optional metadata unavailable'});
 };
 try{
  const file=resolve(temp,'app.mjs');await build({entryPoints:['src/main.jsx'],outfile:file,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react','react-dom','react-dom/client','lucide-react'],loader:{'.css':'empty'},plugins:[{name:'expose-handler',setup(b){b.onLoad({filter:/main\.jsx$/},async()=>({contents:(await readFile('src/main.jsx','utf8')).replace('  async function loadCompanies() {','  window.__restoreTest = onCompanyRestored;\n  async function loadCompanies() {'),loader:'jsx',resolveDir:resolve('src')}));}}]});await act(async()=>{await import(pathToFileURL(file));});
  delay=true;let operation;await act(async()=>{operation=window.__restoreTest('restored');});
  const select=document.querySelector('[aria-label="Choose company"]');assert.ok(select);
  if(restoredRole==='switch')await act(async()=>{select.value='c2';select.dispatchEvent(new window.Event('change',{bubbles:true}));});
  let failure;await act(async()=>{finish();try{await operation;}catch(e){failure=e;}});assert.equal(select.value,restoredRole==='switch'?'c2':outcome==='success'?'restored':'c1');assert.equal(Boolean(failure),restoredRole==='current'&&outcome==='failure');
 }finally{dom.window.close();await rm(temp,{recursive:true,force:true});}
});
