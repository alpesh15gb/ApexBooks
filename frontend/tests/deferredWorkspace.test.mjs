import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import React, { act, useState } from 'react';

const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
Object.assign(globalThis, {window:dom.window, document:dom.window.document, IS_REACT_ACT_ENVIRONMENT:true});
const {createRoot} = await import('react-dom/client');
const temporary = await mkdtemp(resolve('node_modules/.deferred-workspace-'));
await build({stdin:{contents:'export {deferWorkspace} from "./src/DeferredWorkspace.jsx"; export {registerPostingRequest} from "./src/postingRegistry.js";', resolveDir:resolve('.')},outfile:resolve(temporary,'component.mjs'),bundle:true,platform:'node',format:'esm',external:['react','react-dom']});
const {deferWorkspace,registerPostingRequest} = await import(pathToFileURL(resolve(temporary,'component.mjs')));
after(async()=>{dom.window.close();await rm(temporary,{recursive:true,force:true});});

test('feature is requested on first use, shared by concurrent instances and cached on revisit', async()=>{
  let calls=0,finish;
  const Feature=deferWorkspace(()=>{calls++;return new Promise(resolve=>{finish=resolve;});},'Reports');
  assert.equal(calls,0);
  const root=createRoot(document.getElementById('root'));
  await act(async()=>root.render(React.createElement(React.Fragment,null,React.createElement(Feature,{name:'A'}),React.createElement(Feature,{name:'B'}))));
  assert.equal(calls,1);assert.equal(document.querySelectorAll('[aria-busy=true]').length,2);
  await act(async()=>finish({default:({name})=>React.createElement('p',null,'Ready '+name)}));
  assert.match(document.body.textContent,/Ready AReady B/);
  await act(async()=>root.render(null));
  await act(async()=>root.render(React.createElement(Feature,{name:'C'})));
  assert.equal(calls,1);assert.match(document.body.textContent,/Ready C/);
  await act(async()=>root.unmount());
});

test('failed loading keeps the surrounding workspace usable and can retry without reloading', async()=>{
  let calls=0;
  const Feature=deferWorkspace(async()=>{if(++calls===1)throw Error('Offline');return {default:()=>React.createElement('p',null,'Bank ready')};},'Cash & bank');
  const root=createRoot(document.getElementById('root'));
  await act(async()=>root.render(React.createElement('div',null,React.createElement('button',null,'Navigation'),React.createElement(Feature))));
  assert.equal(document.querySelector('[data-workspace-load]').dataset.workspaceLoad,'failed');
  assert.match(document.body.textContent,/Navigation/);
  await act(async()=>[...document.querySelectorAll('button')].find(node=>node.textContent==='Retry loading').click());
  assert.equal(calls,2);assert.match(document.body.textContent,/Bank ready/);
  await act(async()=>root.unmount());
});

test('reload fallback cannot abandon pending postings or an open form', async()=>{
  const Feature=deferWorkspace(async()=>{throw Error('Unavailable');},'Reports');
  const root=createRoot(document.getElementById('root'));
  const unregister=registerPostingRequest({pending:true});
  await act(async()=>root.render(React.createElement(Feature)));
  const reload=()=>[...document.querySelectorAll('button')].find(node=>node.textContent==='Reload app').click();
  await act(async()=>reload());assert.match(document.body.textContent,/pending save before reloading/);
  unregister();
  const overlay=document.createElement('div');overlay.className='overlay';overlay.innerHTML='<div class="modal"></div>';document.body.appendChild(overlay);
  await act(async()=>reload());assert.match(document.body.textContent,/open form before reloading/);
  overlay.remove();await act(async()=>root.unmount());
});

test('feature state survives parent updates and loading completion uses current company props', async()=>{
  let finish;
  const Feature=deferWorkspace(()=>new Promise(resolve=>{finish=resolve;}),'Worklist');
  function Stateful({company}) {const [count,setCount]=useState(0);return React.createElement('button',{onClick:()=>setCount(value=>value+1)},company+':'+count);}
  const root=createRoot(document.getElementById('root'));
  await act(async()=>root.render(React.createElement(Feature,{company:'A'})));
  await act(async()=>root.render(React.createElement(Feature,{company:'B'})));
  await act(async()=>finish({default:Stateful}));
  assert.match(document.body.textContent,/B:0/);
  await act(async()=>document.querySelector('button').click());
  await act(async()=>root.render(React.createElement(Feature,{company:'B'})));
  assert.match(document.body.textContent,/B:1/);
  await act(async()=>root.unmount());
});
