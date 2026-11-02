import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
const temporary=await mkdtemp(resolve('node_modules/.recurring-tests-'));
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/'});
Object.assign(globalThis,{window:dom.window,document:dom.window.document,IS_REACT_ACT_ENVIRONMENT:true});
window.confirm=()=>true;
const outfile=resolve(temporary,'component.mjs');await build({entryPoints:['src/RecurringWorkspace.jsx'],outfile,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react','react-dom','lucide-react']});
const Recurring=(await import(pathToFileURL(outfile))).default;
const template={id:'t1',name:'Monthly review',version:0,draft_kind:'sales_order',party_name:'Synthetic',start_date:'2026-01-31',frequency:'monthly',interval:1,is_active:true,next_due:'2026-11-02',generated_count:0};
const Modal=({children})=>React.createElement('section',{role:'dialog'},children);
const click=async text=>{const button=[...document.querySelectorAll('button')].find(button=>button.textContent.includes(text));assert.ok(button,text);await act(async()=>button.click());};
const apiRead=async path=>path.endsWith('/t1')?{...template,draft:{kind:'sales_order',name:'Synthetic',data:{lines:[{description:'Cable',quantity:'1',rate:'100'}]}}}:path.endsWith('/due')?{rows:[template],business_date:'2026-11-02',timezone:'Asia/Kolkata'}:{templates:[template]};
const props={companyId:'c1',role:'owner',records:[],Modal,onRefresh:async()=>{},onReview:()=>{}};
after(async()=>{dom.window.close();await rm(temporary,{recursive:true,force:true});});
test('opening recurring worklist never generates a draft; viewer can only inspect',async()=>{
 const root=createRoot(document.getElementById('root'));const methods=[];
 await act(async()=>root.render(React.createElement(Recurring,{...props,role:'viewer',api:async(path,options)=>{methods.push(options?.method||'GET');return apiRead(path);}})));
 assert.deepEqual(methods,['GET','GET']);assert.match(document.body.textContent,/Read-only/);assert.equal([...document.querySelectorAll('button')].some(button=>button.textContent.includes('Create draft')),false);
 await click('Inspect template');assert.match(document.body.textContent,/Cable/);assert.equal(document.querySelector('button[type=submit]'),null);await act(async()=>root.unmount());
});
test('uncertain occurrence generation retries the exact date/key and reviews one returned draft',async()=>{
 const root=createRoot(document.getElementById('root'));const writes=[];let reviewed;
 const api=async(path,options)=>{if(options?.method==='POST'){writes.push({path,...options});if(writes.length===1)throw new TypeError('Response lost');return{record:{id:'draft1',kind:'sales_order'},replayed:true};}return apiRead(path);};
 await act(async()=>root.render(React.createElement(Recurring,{...props,api,onReview:record=>{reviewed=record;}})));
 await click('Create draft & review');
 const submit=()=>document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
 await act(async()=>submit());assert.match(document.body.textContent,/response was not confirmed/);assert.equal(document.querySelector('fieldset').disabled,true);
 const before=new window.Event('beforeunload',{cancelable:true});window.dispatchEvent(before);assert.equal(before.defaultPrevented,true);
 await act(async()=>submit());assert.equal(writes.length,2);assert.equal(writes[0].body,writes[1].body);assert.equal(writes[0].headers['Idempotency-Key'],writes[1].headers['Idempotency-Key']);assert.equal(JSON.parse(writes[0].body).occurrence_date,template.next_due);assert.equal(reviewed.id,'draft1');await act(async()=>root.unmount());
});
test('late company refresh cannot reopen a generated draft after leaving the workspace',async()=>{
 const root=createRoot(document.getElementById('root'));let finishRefresh,reviewed=false;
 const api=async(path,options)=>options?.method==='POST'?{record:{id:'draft1'}}:apiRead(path);
 await act(async()=>root.render(React.createElement(Recurring,{...props,api,onRefresh:()=>new Promise(resolve=>{finishRefresh=resolve;}),onReview:()=>{reviewed=true;}})));
 await click('Create draft & review');await act(async()=>document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
 assert.equal(typeof finishRefresh,'function');await act(async()=>root.unmount());await act(async()=>finishRefresh());assert.equal(reviewed,false);
});
test('template source picker excludes posted and already-converted documents',async()=>{
 const root=createRoot(document.getElementById('root'));
 await act(async()=>root.render(React.createElement(Recurring,{...props,api:apiRead,records:[{id:'valid',kind:'estimate',name:'Reviewed quote'},{id:'posted',kind:'sales_invoice',name:'Posted invoice'},{id:'converted',kind:'estimate',name:'Converted quote',converted_to:'invoice'}]})));
 await click('New template');const options=[...document.querySelector('select[name=source_record_id]').options].map(option=>option.value);assert.deepEqual(options,['','valid']);assert.match(document.body.textContent,/Dates are fixed after creating/);await act(async()=>root.unmount());
});
