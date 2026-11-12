import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';
import {build} from 'esbuild';import {JSDOM} from 'jsdom';import React,{act} from 'react';import {createRoot} from 'react-dom/client';
for(const kind of ['receipt','backup','final-save'])test(`session ownership during ${kind}`,async()=>{
 const temp=await mkdtemp(resolve('node_modules/.session-stream-'));const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/'});
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true});localStorage.token='old';
 const oldFetch=globalThis.fetch,oldDigest=crypto.subtle.digest,oldUrl=URL.createObjectURL;let root,finish,cancelled=false,urls=0;
 const bytes=new TextEncoder().encode('%PDF-1.4\nsynthetic\n%%EOF'),digest=await oldDigest.call(crypto.subtle,'SHA-256',bytes),hash=[...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
 const row={id:'receipt',filename:'receipt.pdf',size_bytes:bytes.length,sha256:hash};
 try{
  const outfile=resolve(temp,'scope.mjs');await build({stdin:{contents:"export * from './src/sessionScope.js'; export * from './src/attachmentFiles.js'; export * from './src/backupChunks.js'; export {default as Attachments} from './src/DocumentAttachments.jsx';",resolveDir:process.cwd()},outfile,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react','react-dom','react-dom/client','lucide-react'],loader:{'.css':'empty'}});
  const scope=await import(pathToFileURL(outfile));
  if(kind!=='final-save'){
   let entered;const reading=new Promise(r=>entered=r);const pending=new Promise(r=>finish=r);
   let reads=0;globalThis.fetch=async()=>({headers:new Headers(),body:{getReader:()=>({read:()=>{entered();return reads++ ? Promise.resolve({done:true}) : pending;},cancel:async()=>{cancelled=true;},releaseLock(){}})}});
   const response=await scope.sessionFetch('/api/synthetic');
   const task=kind==='receipt'?scope.verifiedReceiptDownload(response,row):scope.readBackupChunkResponse(response);
   const rejection=assert.rejects(task,/sign-in changed/);await reading;localStorage.token='new';finish({done:false,value:bytes});await rejection;assert.equal(cancelled,true);
  }else{
   let entered;const hashing=new Promise(r=>entered=r);const pending=new Promise(r=>finish=r);
   crypto.subtle.digest=()=>{entered();return pending;};URL.createObjectURL=()=>{urls++;return 'blob:synthetic';};
   const api=async path=>path.endsWith('/download')?new Response(bytes):{attachments:[row],storage:{}};
   root=createRoot(document.getElementById('root'));await act(async()=>root.render(React.createElement(scope.Attachments,{companyId:'c1',recordId:'r1',role:'viewer',api})));
   const button=[...document.querySelectorAll('button')].find(b=>b.textContent==='Download');assert.ok(button);
   await act(async()=>{button.click();await hashing;});localStorage.token='new';
   await act(async()=>{finish(digest);});assert.equal(urls,0);assert.match(document.body.textContent,/sign-in changed/);
  }
 }finally{if(root)await act(async()=>root.unmount());globalThis.fetch=oldFetch;crypto.subtle.digest=oldDigest;URL.createObjectURL=oldUrl;dom.window.close();await rm(temp,{recursive:true,force:true});}
});
