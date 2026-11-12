import test, {after} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {build} from 'esbuild';
import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import {JSDOM} from 'jsdom';

const temporary = await mkdtemp(resolve('node_modules/.workflow-clarity-'));
await build({entryPoints:['src/OpeningStock.jsx','src/MasterForm.jsx','src/ReportLibrary.jsx','src/DocumentWorkbench.jsx'],outdir:temporary,bundle:true,jsx:'automatic',platform:'node',format:'esm',outExtension:{'.js':'.mjs'},external:['react','react-dom','lucide-react']});
const MasterForm = (await import(pathToFileURL(resolve(temporary,'MasterForm.mjs')))).default;
const OpeningStock = (await import(pathToFileURL(resolve(temporary,'OpeningStock.mjs')))).default;
const ReportLibrary = (await import(pathToFileURL(resolve(temporary,'ReportLibrary.mjs')))).default;
const {DocumentIdentity} = await import(pathToFileURL(resolve(temporary,'DocumentWorkbench.mjs')));
after(()=>rm(temporary,{recursive:true,force:true}));

async function mount(Component, props, check) {
  const dom = new JSDOM('<div id="root"></div>',{url:'http://localhost/'});
  Object.assign(globalThis,{window:dom.window,document:dom.window.document,IS_REACT_ACT_ENVIRONMENT:true});
  const root = createRoot(document.getElementById('root'));
  await act(async()=>root.render(React.createElement(Component,props)));
  const click = async label => {
    const button=[...document.querySelectorAll('button')].find(node=>node.textContent.trim()===label || node.getAttribute('aria-label')===label);
    assert.ok(button,`Button: ${label}`);
    await act(async()=>button.click());
  };
  const input = async (selector,value) => {
    const node=document.querySelector(selector);
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(node,value);
    await act(async()=>node.dispatchEvent(new dom.window.Event('input',{bubbles:true})));
    await act(async()=>node.dispatchEvent(new dom.window.Event('change',{bubbles:true})));
  };
  try { await check({dom,click,input}); }
  finally { await act(async()=>root.unmount());dom.window.close(); }
}

test('master saving is single-flight and cannot be dismissed before confirmation',async()=>{
  let saves=0,closes=0,release;
  const pending=new Promise(resolve=>{release=resolve;});
  await mount(MasterForm,{kind:'party',record:{name:'Customer',data:{}},close:()=>closes++,save:async()=>{saves++;await pending;}},async({dom,click})=>{
    const submit=()=>document.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));
    await act(async()=>{submit();submit();});
    assert.equal(saves,1);
    assert.equal(document.querySelector('fieldset').disabled,true);
    await click('Close');await click('Cancel');
    await act(async()=>document.querySelector('.overlay').dispatchEvent(new dom.window.MouseEvent('mousedown',{bubbles:true})));
    assert.equal(closes,0);
    await act(async()=>release());
    await click('Cancel');assert.equal(closes,1);
  });
});

test('whitespace-only master names are rejected without sending a save',async()=>{
  let saves=0;
  await mount(MasterForm,{kind:'party',record:{name:'   ',data:{}},close:()=>{},save:async()=>saves++},async({dom})=>{
    await act(async()=>document.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));
    assert.equal(saves,0);assert.match(document.querySelector('[role="alert"]').textContent,/Enter a party name/);
  });
});

test('a changed master is retained until discard is explicitly confirmed',async()=>{
  let closes=0;
  await mount(MasterForm,{kind:'party',record:{name:'Customer',data:{}},close:()=>closes++,save:async()=>{}},async({dom,click})=>{
    const type=document.querySelector('select[name="party_type"]');
    await act(async()=>{type.value='supplier';type.dispatchEvent(new dom.window.Event('change',{bubbles:true}));});
    await click('Cancel');assert.equal(closes,0);
    assert.match(document.querySelector('[role="alert"]').textContent,/Discard unsaved changes/);
    await click('Keep editing');assert.equal(type.value,'supplier');
    await click('Close');await click('Discard changes');assert.equal(closes,1);
  });
});

test('report shortcuts open the requested report and category filters can be reset',async()=>{
  const selected=[];
  await mount(ReportLibrary,{onSelect:key=>selected.push(key)},async({click})=>{
    const shortcuts=document.querySelectorAll('.report-shortcut');
    assert.equal(shortcuts.length,3);
    await act(async()=>shortcuts[1].click());assert.deepEqual(selected,['ageing']);
    await click('GST preparation');
    assert.equal(document.querySelectorAll('.report-choice').length,4);
    assert.equal(document.querySelectorAll('.report-shortcut').length,0);
    await click('All reports');assert.equal(document.querySelectorAll('.report-choice').length,16);
  });
});

test('document customer validation accepts real names and rejects only whitespace',async()=>{
  const form={name:'Apex Customer',party_phone:'',party_address:'',shipping_address:'',number:'',date:'2026-11-12',due_date:''};
  await mount(DocumentIdentity,{form,setForm:()=>{},change:()=>{},kind:'sales_invoice',company:{tax_mode:'unregistered'}},async()=>{
    const name=document.querySelector('input[name="name"]');
    assert.equal(name.checkValidity(),true);
    name.value='   ';assert.equal(name.checkValidity(),false);
    name.value='Gujarat Trading & Co.';assert.equal(name.checkValidity(),true);
  });
});

test('tracked goods cannot be changed to service while legacy service metadata remains editable',async()=>{
 let saves=0;
 await mount(MasterForm,{kind:'item',record:{name:'Synthetic goods',data:{track_stock:true,item_type:'goods'}},close:()=>{},save:async()=>saves++},async({dom})=>{
  const type=document.querySelector('select[name="item_type"]');await act(async()=>{type.value='services';type.dispatchEvent(new dom.window.Event('change',{bubbles:true}));});await act(async()=>document.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));assert.equal(saves,0);assert.match(document.querySelector('[role=alert]').textContent,/goods only/);
 });
 await mount(MasterForm,{kind:'item',record:{name:'Legacy synthetic service',data:{track_stock:true,item_type:'services'}},close:()=>{},save:async()=>saves++},async({dom})=>{
  assert.match(document.body.textContent,/Existing service stock history requires review/);await act(async()=>document.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));assert.equal(saves,1);
 });
});

test('opening stock excludes service masters and disables an empty goods selection',async()=>{
 await mount(OpeningStock,{items:[{id:'service',name:'Legacy service',data:{item_type:'services'}}],close:()=>{},save:async()=>{}},async()=>{
  assert.equal([...document.querySelectorAll('option')].some(option=>option.value==='service'),false);assert.equal([...document.querySelectorAll('button')].find(button=>button.textContent==='Post opening stock').disabled,true);
 });
});
