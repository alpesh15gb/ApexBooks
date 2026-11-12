import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';
import React,{act} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {stateCodes} from '../src/stateCodes.js';
const temp=await mkdtemp(resolve('node_modules/.workflow-clarity-'));
for(const name of ['StateCodeSelect','NegativeCashNotice','DateRangeFilter'])await build({entryPoints:[`src/${name}.jsx`],outfile:resolve(temp,name+'.mjs'),bundle:true,platform:'node',format:'esm',external:['react','lucide-react']});
const load=async name=>(await import(pathToFileURL(resolve(temp,name+'.mjs')))).default;
const Select=await load('StateCodeSelect'),Notice=await load('NegativeCashNotice'),Dates=await load('DateRangeFilter');
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});
Object.assign(globalThis,{window:dom.window,document:dom.window.document,IS_REACT_ACT_ENVIRONMENT:true});
const {createRoot}=await import('react-dom/client');
after(async()=>{dom.window.close();await rm(temp,{recursive:true,force:true});});
test('state names match backend choices and selection writes only the state code; legacy value survives',async()=>{
 const schema=JSON.parse(await readFile('../backend/gst_export_schema.json','utf8'));assert.deepEqual(stateCodes,schema.master.POS.map(x=>[x.slice(0,2),x.slice(3)]));
 const root=createRoot(document.getElementById('root'));let selected;
 try{await act(async()=>root.render(React.createElement(Select,{value:'24',name:'place_of_supply',onChange:e=>selected=e.target.value})));assert.match(document.querySelector('option:checked').textContent,/Gujarat \(24\)/);await act(async()=>{const select=document.querySelector('select');select.value='27';select.dispatchEvent(new window.Event('change',{bubbles:true}));});assert.equal(selected,'27');
 await act(async()=>root.render(React.createElement(Select,{value:'28',onChange:()=>{}})));assert.equal(document.querySelector('select').value,'28');assert.match(document.querySelector('option:checked').textContent,/Saved code 28/);
 }finally{await act(async()=>root.unmount());}
});
test('negative cash cue uses only loaded negative closing cash and changes no values',()=>{
 for(const value of ['0','100',null,'NaN'])assert.equal(renderToStaticMarkup(React.createElement(Notice,{data:{closing:{cash:value}},through:'2026-04-02'})),'');
 const data={closing:{cash:'-500'}};const markup=renderToStaticMarkup(React.createElement(Notice,{data,through:'2026-04-02'}));assert.match(markup,/02-Apr-2026/);assert.match(markup,/not proof of the cause/);assert.match(markup,/has not been changed/);assert.equal(data.closing.cash,'-500');
});
test('date hints are unambiguous and linked without changing ISO input values',()=>{
 const markup=renderToStaticMarkup(React.createElement(Dates,{value:{period:'custom',from:'2026-04-02',to:'2026-05-03'},onChange:()=>{}}));const doc=new JSDOM(markup).window.document;
 const inputs=[...doc.querySelectorAll('input')];assert.deepEqual(inputs.map(x=>x.value),['2026-04-02','2026-05-03']);for(const input of inputs)assert.match(doc.getElementById(input.getAttribute('aria-describedby')).textContent,/02-Apr-2026 to 03-May-2026/);
});
