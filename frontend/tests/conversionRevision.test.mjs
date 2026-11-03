import test,{after} from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,rm} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';import {build} from 'esbuild';import {JSDOM} from 'jsdom';import React,{act} from 'react';
import {captureConversionSource,conversionBlockReason} from '../src/conversionRevision.js';
const temp=await mkdtemp(resolve('node_modules/.conversion-tests-'));await build({entryPoints:['src/RecordEditor.jsx'],outfile:resolve(temp,'editor.mjs'),bundle:true,platform:'node',format:'esm',external:['react','react-dom','lucide-react']});
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});Object.assign(globalThis,{window:dom.window,document:dom.window.document,IS_REACT_ACT_ENVIRONMENT:true});const {createRoot}=await import('react-dom/client');const Editor=(await import(pathToFileURL(resolve(temp,'editor.mjs')))).default;
after(async()=>{dom.window.close();await rm(temp,{recursive:true,force:true});});
const Modal=({children})=>React.createElement('section',null,children);
const original=Object.freeze({id:'quote1',kind:'estimate',name:'Buyer',data:Object.freeze({version:0,lines:Object.freeze([Object.freeze({description:'Reviewed service',quantity:'1',rate:'100',gst_rate:'0',tax_treatment:'nil_rated'})])})});
const supported={status:'verified',features:['document_conversion_revisions']};
const base={kind:'sales_invoice',source:original,features:supported.features,capabilities:supported,company:{role:'owner',name:'Synthetic',tax_mode:'regular',state_code:'27'},companyId:'c1',records:[],api:async path=>path.endsWith('bank-accounts')?[]:{amount:'100',data:{lines:[]}},Modal,labels:{sales_invoice:'Sales invoices'},documentKinds:['sales_invoice'],money:String,today:()=> '2026-11-03',close:()=>{}};
const submit=()=>act(async()=>document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
const saveButton=()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Save invoice');
test('source snapshot defaults only absent historical revision to zero and leaves edits/create alone',()=>{
 assert.deepEqual(captureConversionSource({id:'old',data:{}},false),{id:'old',version:0});assert.equal(captureConversionSource(original,true),null);assert.equal(captureConversionSource(undefined,false),null);
 for (const version of [null, undefined, '0', -1, 1.5]) assert.match(conversionBlockReason(captureConversionSource({id:'x',data:{version}},false),supported),/invalid/);
 assert.match(conversionBlockReason({id:'x',version:0},{status:'unverified',features:supported.features},supported.features),/could not be verified/);
});
test('conversion sends original reviewed source version and original retry payload despite fresh props',async()=>{
 const root=createRoot(document.getElementById('root'));const writes=[];const save=async(payload,key)=>{writes.push({payload,key});if(writes.length===1){const error=Error('Lost response');error.status=0;throw error;}};
 await act(async()=>root.render(React.createElement(Editor,{...base,save})));
 await submit();assert.equal(writes[0].payload.data.source_document_version,0);assert.equal(writes[0].payload.data.lines[0].rate,'100');
 const newer={...original,data:{...original.data,version:1,lines:[{...original.data.lines[0],rate:'200'}]}};
 await act(async()=>root.render(React.createElement(Editor,{...base,source:newer,save})));await submit();assert.deepEqual(writes[1],writes[0]);assert.equal(original.data.version,0);assert.equal(original.data.lines[0].rate,'100');await act(async()=>root.unmount());
});
test('old, loading and unverified servers block only conversion with distinct retry/upgrade guidance',async()=>{
 for(const [capabilities,pattern] of [[null,/Checking API support/],[{status:'unverified',features:[]},/could not be verified/],[{status:'verified',features:[]},/needs an update/]]){
  const root=createRoot(document.getElementById('root'));let writes=0,retries=0;
  await act(async()=>root.render(React.createElement(Editor,{...base,capabilities,features:[],save:()=>{writes++;},onRetryCapabilities:()=>{retries++;}})));
  assert.equal(saveButton().disabled,true);assert.match(document.body.textContent,pattern);await submit();assert.equal(writes,0);
  await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Check API support again').click());assert.equal(retries,1);
  await act(async()=>root.render(React.createElement(Editor,{...base,capabilities:supported,save:()=>{writes++;}})));assert.equal(saveButton().disabled,false);await submit();assert.equal(writes,1);await act(async()=>root.unmount());
 }
});
test('normal create and existing document edits work without conversion capability and send no conversion token',async()=>{
 for(const edit of [false,true]){const root=createRoot(document.getElementById('root'));let saved;
 await act(async()=>root.render(React.createElement(Editor,{...base,source:edit?original:undefined,edit,capabilities:{status:'unverified',features:[]},features:[],save:value=>{saved=value;}})));
 assert.equal(saveButton().disabled,false);await submit();assert.equal(saved.data.source_document_version,undefined);assert.equal(saved.data.source_document_id,undefined);await act(async()=>root.unmount());}
});
test('only exact source-revision409 releases an uncertain conversion and requires reopening source',async()=>{
 for(const message of ['Conversion source changed; reopen it and review the conversion again','Conversion source revision required; update the app and reopen the source document before converting','This document is already converted','Conversion source changed; reopen it and review the conversion again EXTRA']){
  let attempt=0;const root=createRoot(document.getElementById('root'));const save=async()=>{if(++attempt===1)throw Object.assign(Error('Response lost'),{status:0});throw Object.assign(Error(message),{status:409});};
  await act(async()=>root.render(React.createElement(Editor,{...base,save})));await submit();await submit();
  const definite=message==='Conversion source changed; reopen it and review the conversion again'||message==='Conversion source revision required; update the app and reopen the source document before converting';
  const cancel=[...document.querySelectorAll('button')].find(button=>button.textContent==='Cancel');assert.equal(cancel.disabled,!definite);assert.equal(saveButton().disabled,definite);
  assert.equal(document.querySelector('[name=rate]').value,'100');if(definite)assert.match(document.body.textContent,/Your entered details remain visible/);else assert.match(document.body.textContent,/previous response was not confirmed/);
  await act(async()=>root.unmount());
 }
});
