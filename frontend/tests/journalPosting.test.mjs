import test,{after} from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,rm,readFile} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';import {build} from 'esbuild';import {JSDOM} from 'jsdom';import React,{act} from 'react';
import {captureJournalRequest,sendJournalRequest,journalPostingBlockReason} from '../src/journalPosting.js';
const temp=await mkdtemp(resolve('node_modules/.journal-tests-'));const main=await readFile('src/main.jsx','utf8');
// Compile the actual Ledger implementation, without mounting the unrelated App.
const ledger=main.slice(main.indexOf('function Ledger('),main.indexOf('\nfunction PaymentAllocationSummary'));
const prelude=`import React,{useState,useEffect,useRef} from 'react';import {createRequestScope} from './requestScope.js';import {usePostingRequest,pendingPostingMessage} from './usePostingRequest.js';import {journalPostingBlockReason,captureJournalRequest,sendJournalRequest,isDefiniteJournalConflict,journalReconciliationWarning} from './journalPosting.js';const today=()=> '2026-11-03',money=String;const Empty=()=>null;const Modal=({children,close})=><section role="dialog"><button aria-label="Close reversal" onClick={close}>Close</button>{children}</section>;const api=(...args)=>globalThis.journalTestApi(...args);`;
await build({stdin:{contents:prelude+ledger+'\nexport default Ledger;',resolveDir:resolve('src'),loader:'jsx'},outfile:resolve(temp,'ledger.mjs'),bundle:true,platform:'node',format:'esm',external:['react','react-dom']});
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true});const {createRoot}=await import('react-dom/client');const Ledger=(await import(pathToFileURL(resolve(temp,'ledger.mjs')))).default;
after(async()=>{delete globalThis.journalTestApi;dom.window.close();await rm(temp,{recursive:true,force:true});});
const capability={status:'verified',features:['journal_idempotency']};const entry={date:'2026-11-03',reference:'J1',memo:'Synthetic',debit_account:'a',credit_account:'b',amount:'100'};
const confirmed=(path,options)=>{const body=JSON.parse(options.body);return{id:'confirmed-journal',reference:body.reference.trim(),...(path.endsWith('/reverse')?{reversal_of:'j1'}:{date:body.date})};};
const button=text=>[...document.querySelectorAll('button')].find(b=>b.textContent===text);
const form=()=>[...document.querySelectorAll('form')].find(f=>f.textContent.includes('Debit account'));
async function change(root,label,value){const input=[...root.querySelectorAll('label')].find(l=>l.textContent.trim().startsWith(label)).querySelector('input,select');await act(async()=>{Object.getOwnPropertyDescriptor(input.tagName==='SELECT'?window.HTMLSelectElement.prototype:window.HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new window.Event(input.tagName==='SELECT'?'change':'input',{bubbles:true}));});}
async function setup(write,capabilities=capability){localStorage.token='synthetic-session';const writes=[];globalThis.journalTestApi=async(path,options)=>{if(options?.method){writes.push({path,...options});return write(path,options);}if(path.endsWith('/accounts'))return[{id:'a',code:'A',name:'A'},{id:'b',code:'B',name:'B'}];if(path.endsWith('/journals'))return[{id:'j1',reference:'Original',date:'2026-11-01',lines:[]}];return{accounts:[],total_debit:'0',total_credit:'0'};};const root=createRoot(document.getElementById('root'));let retries=0;const props={companyId:'c1',role:'owner',capabilities,onRetryCapabilities:()=>{retries++;}};await act(async()=>root.render(React.createElement(Ledger,props)));return{root,writes,props,get retries(){return retries;}};}
async function fill(){await change(form(),'Reference','J1');await change(form(),'Memo','Synthetic');await change(form(),'Debit account','a');await change(form(),'Credit account','b');await change(form(),'Amount','100');}
async function submit(target){await act(async()=>target.dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));}
test('journal snapshot freezes exact body/key/session and rejects context changes before sending',async()=>{
 const request=captureJournalRequest('c1',entry,'session');entry.amount='200';assert.equal(JSON.parse(request.body).lines[0].debit,'100');assert.equal(Object.isFrozen(request),true);let sent=0;
 await assert.rejects(sendJournalRequest(()=>sent++,request,'different'),/session changed/);await assert.rejects(sendJournalRequest(()=>sent++,request,'session','c2'),/original company/);assert.equal(sent,0);
 assert.match(journalPostingBlockReason({status:'unverified',features:capability.features}),/could not be verified/);
});
test('unknown create locks fields and retries original journal with same key even after409',async()=>{
 let attempts=0;const view=await setup(async(path,options)=>{if(++attempts===1)throw Object.assign(Error('Response lost'),{status:0});if(attempts===2)throw Object.assign(Error('Period locked'),{status:409});return confirmed(path,options);});await fill();await submit(form());assert.equal(form().querySelector('fieldset').disabled,true);assert.equal(button('Reverse entry').disabled,true);assert.ok(button('Retry original journal'));
 await submit(form());assert.equal(form().querySelector('fieldset').disabled,true);await submit(form());assert.deepEqual(view.writes[0],view.writes[1]);assert.deepEqual(view.writes[0],view.writes[2]);assert.equal(form().querySelector('fieldset').disabled,false);await act(async()=>view.root.unmount());
});
test('unknown reversal cannot close or change details and exact retry recovers original result',async()=>{
 let attempts=0;const view=await setup(async(path,options)=>{if(++attempts===1)throw Error('Response lost');return confirmed(path,options);});await act(async()=>button('Reverse entry').click());let dialog=document.querySelector('[role=dialog]');await change(dialog,'New reference','REV1');await change(dialog,'Reason','Correct synthetic entry');await submit(dialog.querySelector('form'));
 assert.equal(dialog.querySelector('fieldset').disabled,true);assert.equal(button('Cancel').disabled,true);await act(async()=>document.querySelector('[aria-label="Close reversal"]').click());assert.ok(document.querySelector('[role=dialog]'));await submit(dialog.querySelector('form'));assert.deepEqual(view.writes[0],view.writes[1]);assert.match(view.writes[0].path,/c1\/journals\/j1\/reverse$/);assert.equal(document.querySelector('[role=dialog]'),null);await act(async()=>view.root.unmount());
});
test('old/unverified API gates journals and reversals without disabling account creation',async()=>{
 for(const [caps,message]of [[null,/Checking API support/],[{status:'unverified',features:[]},/could not be verified/],[{status:'verified',features:[]},/needs an update/]]){const view=await setup(async()=>({}),caps);assert.equal(button('Post journal').disabled,true);assert.equal(button('Reverse entry').disabled,true);assert.match(document.body.textContent,message);await fill();await submit(form());assert.equal(view.writes.length,0);await act(async()=>button('Check API support again').click());assert.equal(view.retries,1);assert.equal(document.querySelector('form fieldset').disabled,false);await act(async()=>view.root.unmount());}
});
test('session changes cannot silently replay the pending request under a different login',async()=>{
 const view=await setup(async()=>{throw Error('Response lost');});await fill();await submit(form());localStorage.token='different-session';await submit(form());assert.equal(view.writes.length,1);assert.match(document.body.textContent,/session changed/);assert.equal(form().querySelector('fieldset').disabled,true);await act(async()=>view.root.unmount());
});
test('a definitive first-attempt409 preserves inputs but permits correction with a new key',async()=>{
 let attempts=0;const view=await setup(async(path,options)=>{if(++attempts===1)throw Object.assign(Error('Journal reference already exists'),{status:409});return confirmed(path,options);});await fill();await submit(form());assert.equal(form().querySelector('fieldset').disabled,false);assert.ok(button('Post journal'));
 await change(form(),'Reference','J-CORRECTED');await submit(form());assert.equal(JSON.parse(view.writes[0].body).reference,'J1');assert.equal(JSON.parse(view.writes[1].body).reference,'J-CORRECTED');assert.notEqual(view.writes[0].headers['Idempotency-Key'],view.writes[1].headers['Idempotency-Key']);await act(async()=>view.root.unmount());
});
test('pending journal protects tab close and cannot replay into another company',async()=>{
 const view=await setup(async()=>{throw Error('Response lost');});await fill();await submit(form());const event=new window.Event('beforeunload',{cancelable:true});window.dispatchEvent(event);assert.equal(event.defaultPrevented,true);
 await act(async()=>view.root.render(React.createElement(Ledger,{...view.props,companyId:'c2'})));await submit(form());assert.equal(view.writes.length,1);assert.match(document.body.textContent,/original company/);assert.equal(form().querySelector('fieldset').disabled,true);await act(async()=>view.root.unmount());
});
test('only exact proven409 after unknown unlocks with reconciliation acknowledgement before new request',async()=>{
 let attempts=0;const view=await setup(async(path,options)=>{if(++attempts===1)throw Error('Response lost');throw Object.assign(Error('Journal reference already exists'),{status:409});});await fill();await submit(form());await submit(form());
 assert.equal(form().querySelector('fieldset').disabled,false);assert.equal(button('Post journal').disabled,true);assert.match(document.body.textContent,/earlier interrupted attempt may have completed/);assert.equal(view.writes.length,2);await submit(form());assert.equal(view.writes.length,2);
 await act(async()=>button('I reviewed journal history; allow a new request').click());assert.equal(button('Post journal').disabled,false);assert.equal(view.writes.length,2);await act(async()=>view.root.unmount());
});
test('definitive journal conflict classification uses exact messages and status only',async()=>{
 const {isDefiniteJournalConflict}=await import('../src/journalPosting.js');
 const messages=['Journal retry key was used for a different request','Journal reference already exists','Journal is already reversed or is itself a reversal','Reference already exists or journal was already reversed','Date is in a locked accounting period','Reverse source documents through their document workflow'];
 for(const message of messages){assert.equal(isDefiniteJournalConflict({status:409,message}),true);assert.equal(isDefiniteJournalConflict({status:500,message}),false);assert.equal(isDefiniteJournalConflict({status:409,message:message+' EXTRA'}),false);}
});
test('malformed successful response retains original journal and reversal requests until verified replay',async()=>{
 for(const reverse of [false,true]){
  let attempts=0;const view=await setup(async(path,options)=>{if(++attempts===1)return{id:'wrong-result',reference:'different-reference',date:'2026-11-03',reversal_of:'wrong-original'};return confirmed(path,options);});
  let target;
  if(reverse){await act(async()=>button('Reverse entry').click());const dialog=document.querySelector('[role=dialog]');await change(dialog,'New reference','REV-VERIFY');await change(dialog,'Reason','Synthetic correction');target=dialog.querySelector('form');}
  else{await fill();target=form();}
  await submit(target);assert.equal(target.querySelector('fieldset').disabled,true);assert.match(document.body.textContent,/response could not be verified/);await submit(target);assert.deepEqual(view.writes[0],view.writes[1]);await act(async()=>view.root.unmount());
 }
});
test('journal acknowledgements require nonempty id and matching reference/date or reversal origin',async()=>{
 for(const reverse of [false,true]){
  const request=captureJournalRequest('c1',reverse?{date:'2026-11-03',reference:' REV ',reason:'Correction'}:{...entry,reference:' J1 '},'session',reverse?'j1':null);
  const valid=reverse?{id:'id1',reference:'REV',reversal_of:'j1'}:{id:'id1',reference:'J1',date:'2026-11-03'};
  for(const patch of [{id:''},{id:'  '},{id:1},{reference:'WRONG'},reverse?{reversal_of:'j2'}:{date:'2026-11-04'}])await assert.rejects(sendJournalRequest(async()=>({...valid,...patch}),request,'session'),/could not be verified/);
  assert.deepEqual(await sendJournalRequest(async()=>valid,request,'session'),valid);
 }
});
