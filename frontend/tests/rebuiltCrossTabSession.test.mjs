import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';
import {build} from 'esbuild';import {JSDOM} from 'jsdom';import React,{act} from 'react';import {createRoot} from 'react-dom/client';
for(const responseStage of ['headers','body'])test(`session boundary preserves draft and rejects stale ${responseStage}`,async()=>{
 const temp=await mkdtemp(resolve('node_modules/.cross-tab-'));const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/'});
 Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,MutationObserver:dom.window.MutationObserver,requestAnimationFrame:cb=>setTimeout(cb,0),IS_REACT_ACT_ENVIRONMENT:true});localStorage.token='old';
 const oldFetch=globalThis.fetch;let finish;const pending=new Promise(r=>finish=r);let calls=0;
 globalThis.fetch=async()=>{calls++;return responseStage==='headers'?pending:{ok:true,json:()=>pending};};
 let root;
 try{
  const outfile=resolve(temp,'scope.mjs');await build({stdin:{contents:"export {DialogFocus} from './src/WorkspaceBoundary.jsx'; export {default as Boundary} from './src/SessionBoundary.jsx'; export * from './src/sessionScope.js';",resolveDir:process.cwd()},outfile,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react','react-dom','react-dom/client']});
  const scope=await import(pathToFileURL(outfile));root=createRoot(document.getElementById('root'));
  await act(async()=>{root.render(React.createElement(React.Fragment,null,React.createElement(scope.DialogFocus),React.createElement(scope.Boundary,null,React.createElement('input',{defaultValue:'Draft retained'}))));});
  const input=document.querySelector('input');input.value='Unsaved typed draft';
  const request=scope.sessionFetch('/api/synthetic').then(r=>r.json());const rejection=assert.rejects(request,/sign-in changed/);
  await Promise.resolve();localStorage.token='replacement';
  await act(async()=>{window.dispatchEvent(new window.StorageEvent('storage',{key:'token',storageArea:localStorage}));});
  assert.ok(input.closest('[hidden][inert]'));assert.equal(input.value,'Unsaved typed draft');assert.match(document.body.textContent,/Sign-in changed in another tab/);
  await act(async()=>{await assert.rejects(scope.sessionFetch('/api/blocked'),/sign-in changed/);finish(responseStage==='headers'?{ok:true,json:async()=>({secret:'old'})}:{secret:'old'});await rejection;});assert.equal(calls,1);
  await act(async()=>{localStorage.token='old';window.dispatchEvent(new window.Event('focus'));});assert.equal(input.closest('[hidden],[inert]'),null);assert.equal(input.value,'Unsaved typed draft');
  await act(async()=>{localStorage.clear();window.dispatchEvent(new window.StorageEvent('storage',{key:null,storageArea:localStorage}));});assert.ok(input.closest('[hidden]'));
  await act(async()=>{scope.acceptLocalSession();});assert.equal(input.closest('[hidden],[inert]'),null);
 }finally{if(root)await act(async()=>root.unmount());globalThis.fetch=oldFetch;dom.window.close();await rm(temp,{recursive:true,force:true});}
});
