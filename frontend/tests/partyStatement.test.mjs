import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';
import React,{act} from 'react';
import {businessPeriodDates} from '../src/businessDate.js';
const temp=await mkdtemp(resolve('node_modules/.party-statement-tests-'));
await build({entryPoints:['src/PartyStatement.jsx'],outfile:resolve(temp,'component.mjs'),bundle:true,platform:'node',format:'esm',external:['react','react-dom','lucide-react']});
const Component=(await import(pathToFileURL(resolve(temp,'component.mjs')))).default;
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});
Object.assign(globalThis,{window:dom.window,document:dom.window.document,IS_REACT_ACT_ENVIRONMENT:true});
const {createRoot}=await import('react-dom/client');
after(async()=>{dom.window.close();await rm(temp,{recursive:true,force:true});});
const statement={balances:{receivable:100},transactions:[]};
const ledger={opening:{amount:0,side:'Dr'},closing:{amount:100,side:'Dr'},totals:{debit:100,credit:0},rows:[]};
const Modal=({children})=>React.createElement('div',{},children);
const buttons=()=>[...document.querySelectorAll('button')].filter(x=>x.textContent.startsWith('Export'));
async function type(index,value){await act(async()=>{const input=document.querySelectorAll('input')[index];Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new window.Event('input',{bubbles:true}));input.dispatchEvent(new window.Event('change',{bubbles:true}));});}
function harness(api){const root=createRoot(document.getElementById('root'));const render=async(companyId='one')=>act(async()=>root.render(React.createElement(Component,{party:{id:'party',name:'Synthetic'},companyId,api,Modal})));return{root,render};}
test('statement defaults to current India financial year and retains explicit custom dates',async()=>{
 const calls=[];const api=async path=>{calls.push(path);return path.includes('/ledger?')?ledger:statement;};const h=harness(api);
 try{await h.render();const period=businessPeriodDates('fy');assert.deepEqual([...document.querySelectorAll('input')].map(x=>x.value),[period.from,period.to]);assert.match(document.body.textContent,/This financial year/);assert.ok(calls.every(x=>x.endsWith(`from_date=${period.from}&to_date=${period.to}`)));assert.equal(buttons().length,2);assert.match(document.querySelector('.party-ledger-summary').textContent,/Closing ledger balance/);assert.equal(document.querySelector('.party-ledger-summary details').open,false);assert.match(document.querySelector('.party-ledger-summary details').textContent,/receivable/);assert.ok(document.querySelector('.ledger-table'));
 await type(0,'2024-01-01');assert.match(document.body.textContent,/Custom date range/);assert.ok(calls.at(-1).includes('from_date=2024-01-01'));await h.render();assert.equal(document.querySelector('input').value,'2024-01-01');
 }finally{await act(async()=>h.root.unmount());}
});
test('changed range or company hides old balances and exports until both current reads succeed',async()=>{
 let delayed=false;const pending=[];const api=path=>delayed?new Promise((resolve,reject)=>pending.push({path,resolve,reject})):Promise.resolve(path.includes('/ledger?')?ledger:statement);const h=harness(api);
 try{await h.render();assert.equal(buttons().length,2);delayed=true;await type(0,'2024-02-01');assert.equal(buttons().length,0);await h.render('two');assert.equal(buttons().length,0);
 await act(async()=>pending.slice(0,2).forEach(x=>x.resolve(x.path.includes('/ledger?')?ledger:statement)));assert.equal(buttons().length,0);
 await act(async()=>pending[2].resolve(statement));assert.equal(buttons().length,0);await act(async()=>pending[3].reject(Error('Synthetic ledger unavailable')));assert.equal(buttons().length,0);assert.match(document.querySelector('[role=alert]').textContent,/Synthetic ledger unavailable/);
 }finally{await act(async()=>h.root.unmount());}
});
