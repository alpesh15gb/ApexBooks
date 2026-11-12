import test from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,rm} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';import {build} from 'esbuild';import {JSDOM} from 'jsdom';import React,{act} from 'react';
import {masterImportStore} from '../src/masterImportRecovery.js';
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,sessionStorage:dom.window.sessionStorage,IS_REACT_ACT_ENVIRONMENT:true});localStorage.token='header.'+btoa(JSON.stringify({sub:'synthetic-actor'}))+'.signature';const {createRoot}=await import('react-dom/client');const temp=await mkdtemp(resolve('node_modules/.master-recovery-'));const file=resolve(temp,'master.mjs');await build({entryPoints:['src/MasterImport.jsx'],outfile:file,bundle:true,platform:'node',format:'esm',external:['react']});const Master=(await import(pathToFileURL(file))).default;
async function settled(){for(let i=0;i<100 && document.body.textContent.includes('Processing ');i++)await act(async()=>new Promise(r=>setTimeout(r,2)));assert.equal(document.body.textContent.includes('Processing '),false);}
const find=text=>[...document.querySelectorAll('button')].find(b=>b.textContent===text);
async function choose(value='name,phone\nSynthetic private party,00123') {const bytes=new TextEncoder().encode(value);const input=document.querySelector('input[type=file]');Object.defineProperty(input,'files',{configurable:true,value:[{size:bytes.length,arrayBuffer:async()=>bytes.buffer}]});await act(async()=>input.dispatchEvent(new window.Event('change',{bubbles:true})));await settled();}
async function mount(extra={}) {const root=createRoot(document.getElementById('root'));await act(async()=>root.render(React.createElement(Master,{companyId:'a',role:'owner',receiptSupport:true,onImported:async()=>{},...extra})));return root;}
for(const mode of ['lookup','retry'])test(`unknown import survives remount and recovers by ${mode}`,async()=>{
 sessionStorage.clear();let commits=[],gets=0;globalThis.fetch=async(url,options)=>{if(options.method==='POST'){const body=JSON.parse(options.body);if(body.dry_run)return {ok:true,status:200,json:async()=>({dry_run:true,ready:1,duplicates:0,errors:[]})};commits.push({body,key:options.headers['Idempotency-Key']});if(commits.length===1)throw TypeError('Lost response');return {ok:true,status:200,json:async()=>({dry_run:false,ready:1,created:1,duplicates:0,errors:[],operation_key:commits[0].key,record_ids:['one']})};}gets++;return {ok:mode==='lookup',status:mode==='lookup'?200:404,json:async()=>({dry_run:false,ready:1,created:1,duplicates:0,errors:[],operation_key:commits[0].key,record_ids:['one']})};};
 let root=await mount();try{
 await choose();await act(async()=>find('Import 1 records').click());await settled();assert.equal(commits.length,1);assert.equal(document.querySelector('select').disabled,true);const stored=sessionStorage.getItem(sessionStorage.key(0));assert.doesNotMatch(stored,/Synthetic private party|00123|signature|rows|token/);assert.equal(Object.keys(JSON.parse(stored)).sort().join(','),'hash,key,kind');
 await act(async()=>root.unmount());root=await mount();assert.equal(find('Retry original import').disabled,true);
 await act(async()=>{find('Check original import').click();find('Check original import').click();});assert.equal(gets,1);
 if(mode==='retry'){
 assert.match(document.body.textContent,/does not prove failure/);await choose('name,phone\nChanged party,999');assert.match(document.body.textContent,/does not match/);assert.equal(find('Retry original import').disabled,true);
 await choose();assert.equal(find('Retry original import').disabled,false);await act(async()=>{find('Retry original import').click();find('Retry original import').click();});assert.equal(commits.length,2);assert.deepEqual(commits[1],commits[0]);
 }else assert.equal(commits.length,1);
 assert.equal(sessionStorage.length,0);assert.equal(find('Check original import'),undefined);
 }finally{await act(async()=>root.unmount());}
});
test('reference storage is isolated by actor and company and refuses overwrite',()=>{
 sessionStorage.clear();const marker={key:'12345678-1234-4234-8234-123456789abc',hash:'a'.repeat(64),kind:'party'};const first=masterImportStore('a',localStorage.token);first.save(marker);assert.deepEqual(first.read(),marker);assert.equal(masterImportStore('b',localStorage.token).read(),null);assert.equal(masterImportStore('a','header.'+btoa(JSON.stringify({sub:'other-actor'}))+'.sig').read(),null);assert.throws(()=>first.save({...marker,key:'22345678-1234-4234-8234-123456789abc'}),/Recover the previous/);first.clear('wrong');assert.ok(first.read());first.clear(marker.key);assert.equal(first.read(),null);
});
test('unsupported server never receives a receipt key',async()=>{
 sessionStorage.clear();let headers;globalThis.fetch=async(url,options)=>{headers=options.headers;const body=JSON.parse(options.body);return {ok:true,status:200,json:async()=>({dry_run:body.dry_run,ready:1,duplicates:0,errors:[]})};};const root=await mount({receiptSupport:false});try{await choose();await act(async()=>find('Import 1 records').click());await settled();assert.equal(headers['Idempotency-Key'],undefined);assert.equal(sessionStorage.length,0);assert.match(document.body.textContent,/does not advertise exact import recovery/);}finally{await act(async()=>root.unmount());}
});
test.after(async()=>{dom.window.close();await rm(temp,{recursive:true,force:true});});

test('storage failure blocks commit before POST and never stores the payload',async()=>{
 const original=globalThis.sessionStorage;globalThis.sessionStorage={getItem:()=>null,setItem:()=>{throw Error('Recovery storage unavailable');},removeItem:()=>{}};let commits=0;
 globalThis.fetch=async(url,options)=>{const body=JSON.parse(options.body);if(!body.dry_run)commits++;return {ok:true,status:200,json:async()=>({dry_run:true,ready:1,duplicates:0,errors:[]})};};
 const root=await mount();try{await choose();await act(async()=>find('Import 1 records').click());await settled();assert.equal(commits,0);assert.match(document.body.textContent,/Recovery storage unavailable/);}finally{await act(async()=>root.unmount());globalThis.sessionStorage=original;}
});
for(const retry of [false,true])test(`definitive rejection ${retry?'after unknown remains frozen':'before unknown permits correction'}`,async()=>{
 sessionStorage.clear();let commits=0;globalThis.fetch=async(url,options)=>{const body=JSON.parse(options.body);if(body.dry_run)return {ok:true,status:200,json:async()=>({dry_run:true,ready:1,duplicates:0,errors:[]})};commits++;if(retry&&commits===1)throw TypeError('Lost response');return {ok:false,status:422,json:async()=>({detail:'Synthetic rejection'})};};
 const root=await mount();try{await choose();await act(async()=>find('Import 1 records').click());await settled();if(retry)await act(async()=>find('Retry original import').click());assert.equal(sessionStorage.length,retry?1:0);assert.equal(!!find('Check original import'),retry);}finally{await act(async()=>root.unmount());}
});
