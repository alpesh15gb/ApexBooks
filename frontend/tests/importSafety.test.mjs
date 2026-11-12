import test, {after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from 'esbuild';
import React, {act} from 'react';
import {JSDOM} from 'jsdom';

const dom = new JSDOM('<div id="root"></div>',{url:'http://localhost/'});
Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true});
const {createRoot}=await import('react-dom/client');
const temporary = await mkdtemp(resolve('node_modules/.import-safety-'));
await build({entryPoints:['src/MasterImport.jsx','src/StatementImportPreview.jsx','src/BackupRestore.jsx'],outdir:temporary,bundle:true,platform:'node',format:'esm',outExtension:{'.js':'.mjs'},external:['react','react-dom','lucide-react']});
const MasterImport=(await import(pathToFileURL(resolve(temporary,'MasterImport.mjs')))).default;
const StatementImport=(await import(pathToFileURL(resolve(temporary,'StatementImportPreview.mjs')))).default;
const BackupRestore=(await import(pathToFileURL(resolve(temporary,'BackupRestore.mjs')))).default;
after(async()=>{dom.window.close();await rm(temporary,{recursive:true,force:true});});
const button=label=>[...document.querySelectorAll('button')].find(node=>node.textContent.trim()===label||node.getAttribute('aria-label')===label);
const click=async label=>{assert.ok(button(label),label);await act(async()=>button(label).click());};
const change=async(node,value)=>{Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(node,value);await act(async()=>node.dispatchEvent(new dom.window.Event('input',{bubbles:true})));};
async function choose(file) {
 const input=document.querySelector('input[type="file"]');
 Object.defineProperty(input,'files',{configurable:true,value:[file]});
 await act(async()=>input.dispatchEvent(new dom.window.Event('change',{bubbles:true})));
}

test('master import freezes record type from file read through preview and commit',async()=>{
 const root=createRoot(document.getElementById('root'));const previous=globalThis.fetch;
 let read,finish,imported=0;const requests=[];
 const file={name:'parties.csv',size:25,arrayBuffer:()=>new Promise(resolve=>{read=resolve;})};
 globalThis.fetch=async(path,options)=>{const body=JSON.parse(options.body);requests.push(body);if(body.dry_run)return{ok:true,json:async()=>({dry_run:true,ready:1,duplicates:0,errors:[]})};await new Promise(resolve=>{finish=resolve;});return{ok:true,json:async()=>({ready:1,duplicates:0,errors:[]})};};
 try {
   await act(async()=>root.render(React.createElement(MasterImport,{companyId:'company',role:'owner',onImported:()=>imported++})));
   await choose(file);const kind=document.querySelector('select');assert.equal(kind.disabled,true);
   await act(async()=>{kind.value='item';kind.dispatchEvent(new dom.window.Event('change',{bubbles:true}));});
   await act(async()=>read(new TextEncoder().encode('name,party_type\nCustomer,customer\n').buffer));
   assert.equal(requests[0].kind,'party');assert.equal(kind.value,'party');
   await act(async()=>{button('Import 1 records').click();button('Import 1 records').click();});
   assert.equal(requests.length,2);assert.equal(requests[1].kind,'party');assert.equal(kind.disabled,true);
   await act(async()=>finish());assert.equal(imported,1);
 } finally {await act(async()=>root.unmount());globalThis.fetch=previous;}
});

test('bank import locks mapping and dismiss controls and retries the exact reviewed rows',async()=>{
 const root=createRoot(document.getElementById('root'));let completePreview,closed=0;const commits=[];
 const file={name:'bank.csv',size:60,arrayBuffer:async()=> new TextEncoder().encode('date,description,amount\n2026-11-12,Customer receipt,100\n').buffer};
 const api=async(path,options)=>{const body=JSON.parse(options.body);if(body.dry_run)return new Promise(resolve=>{completePreview=resolve;});commits.push(options.body);if(commits.length===1)throw new TypeError('Response lost');return{added:0,duplicates:1};};
 try {
   await act(async()=>root.render(React.createElement(StatementImport,{file,companyId:'company',bankId:'bank',bankName:'Current account',api,onClose:()=>closed++,onImported:async()=>{}})));
   await click('Validate mapped rows');assert.ok([...document.querySelectorAll('select')].every(node=>node.disabled));assert.equal(button('Close').disabled,true);
   await act(async()=>completePreview({added:1,duplicates:0}));
   await click('Import 1 transactions');assert.equal(button('Close').disabled,true);assert.equal(button('Cancel').disabled,true);
   await click('Retry same import');assert.deepEqual(commits[0],commits[1]);assert.equal(closed,1);
 } finally {await act(async()=>root.unmount());}
});

test('legacy backup restore freezes validated inputs and replays an uncertain commit',async()=>{
 const root=createRoot(document.getElementById('root'));const previous=globalThis.fetch;const commits=[];let restored='';
 globalThis.fetch=async(path,options)=>{
   if(path.endsWith('/preview'))return{ok:true,json:async()=>({digest:'digest',company_name:'Source',counts:{records:1,journals:1,stock_movements:0}})};
   commits.push(options.body);if(commits.length===1)throw new TypeError('Response lost');
   return{ok:true,json:async()=>({company_id:'restored'})};
 };
 try {
   await act(async()=>root.render(React.createElement(BackupRestore,{companyId:'company',role:'owner',onRestored:id=>{restored=id;}})));
   await change(document.querySelector('input[maxlength="120"]'),'Restored books');
   await choose({name:'backup.gz',size:3,arrayBuffer:async()=>new Uint8Array([31,139,0]).buffer});
   await act(async()=>document.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));
   await click('Restore as separate company');
   assert.ok([...document.querySelectorAll('input')].every(node=>node.disabled));
   await click('Retry same restore');assert.deepEqual(commits[0],commits[1]);assert.equal(restored,'restored');
 } finally {await act(async()=>root.unmount());globalThis.fetch=previous;}
});
test('bank CSV rejects text after quoted description before any preview request',async()=>{
 const root=createRoot(document.getElementById('root'));let requests=0;
 const text='date,description,amount\n2026-11-12,"Receipt"junk,100\n';
 try{
 await act(async()=>root.render(React.createElement(StatementImport,{file:{name:'bank.csv',size:text.length,text:async()=>text,arrayBuffer:async()=>new TextEncoder().encode(text).buffer},companyId:'company',bankId:'bank',bankName:'Bank',api:async()=>{requests++;return{};},onClose:()=>{},onImported:()=>{}})));
 assert.match(document.body.textContent,/unexpected text after a closing quote/);assert.equal(requests,0);assert.equal(button('Validate mapped rows').disabled,true);
 }finally{await act(async()=>root.unmount());}
});
for(const [label,bytes,expected] of [
 ['invalid UTF-8',new Uint8Array([0x64,0x61,0x74,0x65,0x2c,0x96]),/encoding is invalid/],
 ['quote in bare field',new TextEncoder().encode('date,description,amount\n2026-11-12,Rec"eipt,100'),/quote must begin a field/],
 ['unclosed quote',new TextEncoder().encode('date,description,amount\n2026-11-12,"Receipt,100'),/unclosed quoted field/],
])test(`bank CSV blocks ${label} before preview`,async()=>{
 const root=createRoot(document.getElementById('root'));let requests=0;
 try{await act(async()=>root.render(React.createElement(StatementImport,{file:{name:'bad.csv',size:bytes.length,arrayBuffer:async()=>bytes.buffer},companyId:'company',bankId:'bank',bankName:'Bank',api:async()=>{requests++;},onClose:()=>{},onImported:()=>{}})));assert.match(document.body.textContent,expected);assert.equal(button('Validate mapped rows').disabled,true);assert.equal(requests,0);}finally{await act(async()=>root.unmount());}
});
for(const sep of [',',';','\t'])test(`bank CSV preserves BOM quoted multiline description with ${JSON.stringify(sep)} separator`,async()=>{
 const root=createRoot(document.getElementById('root'));let preview;
 const text='\uFEFF'+['date','description','amount'].join(sep)+'\r\n'+['2026-11-12','"Receipt, with ""quote""\r\nnext line"','100'].join(sep)+'\r\n';const bytes=new TextEncoder().encode(text);
 try{await act(async()=>root.render(React.createElement(StatementImport,{file:{name:'valid.csv',size:bytes.length,arrayBuffer:async()=>bytes.buffer},companyId:'company',bankId:'bank',bankName:'Bank',api:async(path,options)=>{preview=JSON.parse(options.body);return{added:1,duplicates:0};},onClose:()=>{},onImported:()=>{}})));await click('Validate mapped rows');assert.equal(preview.dry_run,true);assert.equal(preview.lines[0].description,'Receipt, with "quote"\r\nnext line');assert.equal(preview.lines[0].amount,'100');}finally{await act(async()=>root.unmount());}
});
