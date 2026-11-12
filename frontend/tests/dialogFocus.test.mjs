import test from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,rm} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';import {build} from 'esbuild';import {JSDOM} from 'jsdom';import React,{act} from 'react';
const dom=new JSDOM('<button id="trigger">Open</button><div id="root"></div>',{url:'http://localhost'});const frames=[];
Object.assign(globalThis,{window:dom.window,document:dom.window.document,MutationObserver:dom.window.MutationObserver,requestAnimationFrame:callback=>{frames.push(callback);},IS_REACT_ACT_ENVIRONMENT:true});
const {createRoot}=await import('react-dom/client');const tmp=await mkdtemp(resolve('node_modules/.dialog-focus-'));const outfile=resolve(tmp,'component.mjs');await build({entryPoints:['src/WorkspaceBoundary.jsx'],outfile,bundle:true,platform:'node',format:'esm',external:['react','react-dom']});const {DialogFocus}=await import(pathToFileURL(outfile));
test('deferred dialog autofocus preserves newer user or child focus',async()=>{
 const root=createRoot(document.getElementById('root'));document.getElementById('trigger').focus();
 await act(async()=>root.render(React.createElement(React.Fragment,null,React.createElement(DialogFocus),React.createElement('div',{className:'overlay'},React.createElement('div',{className:'modal'},React.createElement('button',null,'Close'),React.createElement('select',{'aria-label':'Document 2'},React.createElement('option',null,'Choose')))))));
 assert.ok(frames.length);const select=document.querySelector('select');select.focus();
 await act(async()=>{for(const callback of frames.splice(0))callback();});assert.equal(document.activeElement,select);
 await act(async()=>root.unmount());
});
test('nested dialog traps keyboard focus, closes only foreground and restores parent then opener',async()=>{
 const root=createRoot(document.getElementById('root'));const trigger=document.getElementById('trigger');trigger.focus();
 let nested=false,open=true,closed=0;
 const draw=()=>root.render(React.createElement(React.Fragment,null,React.createElement(DialogFocus),open&&React.createElement('div',{className:'overlay'},React.createElement('div',{className:'modal'},React.createElement('button',{id:'parent-open'},'Open nested'),React.createElement('button',{'aria-label':'Close',onClick:()=>{open=false;draw();}},'Close parent'))),nested&&React.createElement('div',{className:'overlay'},React.createElement('div',{className:'modal'},React.createElement('button',{disabled:true},'Unavailable'),React.createElement('button',{id:'first'},'First'),React.createElement('button',{id:'last','aria-label':'Close',onClick:()=>{nested=false;closed++;draw();}},'Close nested')))));
 const flush=async()=>{for(const node of document.querySelectorAll('button'))node.getClientRects=()=>[{width:100,height:30}];await act(async()=>{for(const callback of frames.splice(0))callback();});};
 await act(async()=>draw());await flush();const parent=document.getElementById('parent-open');parent.focus();
 await act(async()=>{nested=true;draw();});await flush();assert.equal(document.activeElement.id,'first');assert.ok(parent.closest('[inert]'));
 document.getElementById('last').focus();await act(async()=>document.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true})));assert.equal(document.activeElement.id,'first');
 await act(async()=>document.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Tab',shiftKey:true,bubbles:true,cancelable:true})));assert.equal(document.activeElement.id,'last');
 await act(async()=>document.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true})));await flush();assert.equal(closed,1);assert.equal(document.activeElement,parent);assert.equal(parent.closest('[inert]'),null);
 await act(async()=>document.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true})));await flush();assert.equal(document.activeElement,trigger);assert.equal(trigger.hasAttribute('inert'),false);
 await act(async()=>root.unmount());
});
test.after(async()=>{dom.window.close();await rm(tmp,{recursive:true,force:true});});
