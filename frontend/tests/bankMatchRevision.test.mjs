import test,{after} from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,rm} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';import {build} from 'esbuild';import {JSDOM} from 'jsdom';import React,{act} from 'react';
import {captureBankUnmatch,bankUnmatchBlockReason} from '../src/bankMatchRevision.js';
const temp=await mkdtemp(resolve('node_modules/.bank-cas-tests-'));
await build({entryPoints:['src/BankWorkspace.jsx'],outfile:resolve(temp,'bank.mjs'),bundle:true,platform:'node',format:'esm',external:['react','react-dom','lucide-react'],plugins:[{name:'only-bank-controls',setup(build){build.onResolve({filter:/\/(CashBook|CashTransfer|StatementImportPreview)\.jsx$/},()=>({path:'stub',namespace:'test'}));build.onLoad({filter:/.*/,namespace:'test'},()=>({contents:'export default function Stub(){return null}',loader:'js'}));}}]});
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true});const {createRoot}=await import('react-dom/client');const Bank=(await import(pathToFileURL(resolve(temp,'bank.mjs')))).default;
const previousFetch=globalThis.fetch;after(async()=>{globalThis.fetch=previousFetch;dom.window.close();await rm(temp,{recursive:true,force:true});});
const capability={status:'verified',features:['bank_match_revisions']};const original={id:'line1',description:'Synthetic matched line',date:'2026-11-01',amount:'100',remaining_amount:'0',matched_record_id:'payment1',match_revision:2};
const button=text=>[...document.querySelectorAll('button')].find(button=>button.textContent.includes(text));
const response=(value,status=200)=>({ok:status<400,status,json:async()=>value});
async function setup({capabilities=capability,line=original,deleteRequest=async()=>response({}),company='c1'}={}){
 const calls=[],getLines=()=>typeof line==='function'?line():line;
 globalThis.fetch=async(path,options={})=>{calls.push({path,...options});if(options.method==='DELETE')return deleteRequest(path,options);if(path.includes('/bank-accounts'))return response([{id:'default',name:'Synthetic bank'}]);if(path.includes('/bank-statement?'))return response([getLines()]);if(path.includes('/reviews?'))return response([]);return response({});};
 const root=createRoot(document.getElementById('root'));let retries=0;const props={companyId:company,records:[],role:'owner',capabilities,onSaved:()=>{},onRetryCapabilities:()=>{retries++;}};
 await act(async()=>root.render(React.createElement(Bank,props)));return{root,calls,props,get retries(){return retries;}};
}
test('capture is immutable, uses reviewed record/revision, and never defaults malformed revision',()=>{
 const line={...original};const operation=captureBankUnmatch('c1',line);line.match_revision=8;line.matched_record_id='other';assert.equal(Object.isFrozen(operation),true);assert.deepEqual(JSON.parse(operation.body),{expected_record_id:'payment1',expected_match_revision:2});
 for(const revision of [undefined,null,'2',-1,1.5,NaN])assert.throws(()=>captureBankUnmatch('c1',{...original,match_revision:revision}),/missing or invalid/);
 assert.match(bankUnmatchBlockReason({status:'unverified',features:['bank_match_revisions']}),/could not be verified/);
});
test('old, unavailable and pending capability checks block unmatch without disabling unrelated review',async()=>{
 for(const [capabilities,pattern]of [[null,/Checking API support/],[{status:'unverified',features:[]},/could not be verified/],[{status:'verified',features:[]},/needs an update/]]){
  const view=await setup({capabilities});assert.equal(button('Matched · Unmatch').disabled,true);assert.equal(button('Save review through').disabled,false);assert.match(document.body.textContent,pattern);
  await act(async()=>button('Check API support again').click());assert.equal(view.retries,1);assert.equal(view.calls.filter(call=>call.method==='DELETE').length,0);await act(async()=>view.root.unmount());
 }
 const view=await setup({line:{...original,match_revision:null}});assert.equal(button('Matched · Unmatch').disabled,true);assert.match(document.body.textContent,/revision is missing or invalid/);await act(async()=>view.root.unmount());
});
test('uncertain unmatch retries exact old body and conflict reload preserves replacement match',async()=>{
 let current={...original},attempt=0;
 const view=await setup({line:()=>current,deleteRequest:async()=>{if(++attempt===1){current={...original,matched_record_id:'payment2',match_revision:4};throw Error('Response lost');}return response({detail:'Bank match changed; reload the statement and review its current match'},409);}});
 await act(async()=>button('Matched · Unmatch').click());assert.ok(button('Retry original unmatch'));assert.equal(button('Matched · Unmatch').disabled,true);
 await act(async()=>button('Retry original unmatch').click());const deletes=view.calls.filter(call=>call.method==='DELETE');assert.equal(deletes.length,2);assert.equal(deletes[0].body,deletes[1].body);assert.equal(JSON.parse(deletes[1].body).expected_record_id,'payment1');assert.equal(button('Retry original unmatch'),undefined);assert.match(document.body.textContent,/No newer match was removed/);
 await act(async()=>button('Matched · Unmatch').click());assert.equal(JSON.parse(view.calls.filter(call=>call.method==='DELETE')[2].body).expected_record_id,'payment2');assert.equal(JSON.parse(view.calls.filter(call=>call.method==='DELETE')[2].body).expected_match_revision,4);await act(async()=>view.root.unmount());
});
test('late old-company unmatch response cannot reload or warn inside new company',async()=>{
 let finish;const view=await setup({deleteRequest:()=>new Promise(resolve=>{finish=resolve;})});
 await act(async()=>button('Matched · Unmatch').click());await act(async()=>view.root.render(React.createElement(Bank,{...view.props,companyId:'c2'})));
 const count=view.calls.filter(call=>call.path.includes('/c2/')).length;
 await act(async()=>finish(response({detail:'Bank match changed; reload the statement and review its current match'},409)));
 assert.equal(view.calls.filter(call=>call.path.includes('/c2/')).length,count);assert.doesNotMatch(document.body.textContent,/No newer match|response was not confirmed/);assert.equal(button('Matched · Unmatch').disabled,false);await act(async()=>view.root.unmount());
});
test('allocation-ID deletion remains available on old API and keeps its original endpoint/body',async()=>{
 const view=await setup({capabilities:{status:'verified',features:[]},line:{...original,matched_record_id:null,allocations:[{id:'allocation1',record_id:'payment1',amount:'100',name:'Synthetic payment'}]}});
 assert.equal(button('Remove').disabled,false);await act(async()=>button('Remove').click());const request=view.calls.find(call=>call.method==='DELETE');assert.equal(request.path,'/api/companies/c1/bank-statement/allocations/allocation1');assert.equal(request.body,undefined);await act(async()=>view.root.unmount());
});
