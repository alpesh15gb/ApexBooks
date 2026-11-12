import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';
import React,{act} from 'react';
const temp=await mkdtemp(resolve('node_modules/.journal-source-'));
await build({entryPoints:['src/JournalSource.jsx'],outfile:resolve(temp,'component.mjs'),bundle:true,platform:'node',format:'esm',external:['react']});
const Component=(await import(pathToFileURL(resolve(temp,'component.mjs')))).default;
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});
Object.assign(globalThis,{window:dom.window,document:dom.window.document,IS_REACT_ACT_ENVIRONMENT:true});
const {createRoot}=await import('react-dom/client');
after(async()=>{dom.window.close();await rm(temp,{recursive:true,force:true});});
test('verified source has recognizable voucher, cancelled status and read-only detail callback',async()=>{
 const root=createRoot(document.getElementById('root'));let opened;
 try{await act(async()=>root.render(React.createElement(Component,{journal:{reference:'AUTO:uuid',source_document:{id:'document',kind:'sales_invoice',number:'INV-9',name:'Buyer',cancelled:true}},onOpen:value=>opened=value})));
 assert.match(document.body.textContent,/INV-9 · Buyer/);assert.match(document.body.textContent,/Cancelled/);assert.equal(document.querySelector('details').open,false);await act(async()=>document.querySelector('button').click());assert.deepEqual(opened,{id:'document'});
 await act(async()=>root.render(React.createElement(Component,{journal:{reference:'AUTO:lookalike',source_record_id:null,source_document:null}})));assert.equal(document.querySelector('button'),null);assert.match(document.body.textContent,/AUTO:lookalike/);
 }finally{await act(async()=>root.unmount());}
});
