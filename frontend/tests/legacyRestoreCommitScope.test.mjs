import test from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,rm} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';import {build} from 'esbuild';import {JSDOM} from 'jsdom';import React,{act} from 'react';
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true});localStorage.token='original';const {createRoot}=await import('react-dom/client');const temp=await mkdtemp(resolve('node_modules/.restore-commit-'));const file=resolve(temp,'backup.mjs');await build({entryPoints:['src/BackupRestore.jsx'],outfile:file,bundle:true,platform:'node',format:'esm',external:['react','react-dom','lucide-react']});const Backup=(await import(pathToFileURL(file))).default;

for(const outcome of ['success','failure'])for(const transition of ['company','role-back','unmount','current'])test(`restore commit ${outcome} scoped to ${transition}`,async t=>{
localStorage.token='original';let finish,fail,callbacks=0,posts=0;const report={digest:'synthetic',company_name:'Source',counts:{records:1,journals:1,stock_movements:0}};
globalThis.fetch=async url=>({ok:true,status:200,json:()=>url.endsWith('/commit')?(posts++,new Promise((r,j)=>{finish=r;fail=j;})):Promise.resolve(report)});
const root=createRoot(document.getElementById('root'));let gone=false;t.after(async()=>{if(!gone)await act(async()=>root.unmount());});const render=(companyId='a',role='owner')=>root.render(React.createElement(Backup,{companyId,role,onRestored:async()=>{callbacks++;}}));await act(async()=>render());
const name=document.querySelector('input[maxlength="120"]');await act(async()=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(name,'Restored');name.dispatchEvent(new window.Event('input',{bubbles:true}));});
const input=document.querySelector('input[type=file]');Object.defineProperty(input,'files',{configurable:true,value:[{size:3,arrayBuffer:async()=>new Uint8Array([31,139,0]).buffer}]});await act(async()=>input.dispatchEvent(new window.Event('change',{bubbles:true})));await act(async()=>document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Restore as separate company').click());assert.equal(posts,1);
if(transition==='company')await act(async()=>render('b'));if(transition==='role-back'){await act(async()=>render('a','viewer'));await act(async()=>render());}if(transition==='unmount'){await act(async()=>root.unmount());gone=true;}
await act(async()=>outcome==='success'?finish({company_id:'restored'}):fail(Error('OBSOLETE COMMIT ERROR')));
assert.equal(callbacks,transition==='current'&&outcome==='success'?1:0);assert.equal(document.body.textContent.includes('OBSOLETE COMMIT ERROR'),transition==='current'&&outcome==='failure');assert.equal(posts,1);
});test.after(async()=>{dom.window.close();await rm(temp,{recursive:true,force:true});});

test('legacy confirmed restore survives navigation failure and reopens without another commit',async t=>{
localStorage.token='original';let posts=0,opens=0;const report={digest:'synthetic',company_name:'Source',counts:{records:1,journals:1,stock_movements:0}};
globalThis.fetch=async url=>({ok:true,status:200,json:async()=>url.endsWith('/commit')?(posts++,{company_id:'restored'}):report});
const root=createRoot(document.getElementById('root'));t.after(async()=>act(async()=>root.unmount()));await act(async()=>root.render(React.createElement(Backup,{companyId:'a',role:'owner',onRestored:async id=>{assert.equal(id,'restored');if(++opens===1)throw Error('List unavailable');}})));
const name=document.querySelector('input[maxlength="120"]');await act(async()=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(name,'Restored');name.dispatchEvent(new window.Event('input',{bubbles:true}));});
const input=document.querySelector('input[type=file]');Object.defineProperty(input,'files',{configurable:true,value:[{size:3,arrayBuffer:async()=>new Uint8Array([31,139,0]).buffer}]});await act(async()=>input.dispatchEvent(new window.Event('change',{bubbles:true})));await act(async()=>document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
const find=text=>[...document.querySelectorAll('button')].find(b=>b.textContent===text);
await act(async()=>find('Restore as separate company').click());assert.equal(posts,1);assert.ok(find('Open restored company'));assert.equal(find('Restore as separate company'),undefined);
await act(async()=>{find('Open restored company').click();find('Open restored company').click();});assert.equal(opens,2);assert.equal(posts,1);assert.doesNotMatch(document.body.textContent,/List unavailable/);
});
