import { CORE_ENHANCEMENTS } from '../src/capabilities.js';
import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
const temp = await mkdtemp(resolve('node_modules/.everyday-tests-'));
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/' });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import('react-dom/client');
async function component(name) { const outfile = resolve(temp, `${name}.mjs`); await build({ entryPoints: [`src/${name}.jsx`], outfile, bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', external: ['react', 'react-dom', 'lucide-react'] }); return (await import(pathToFileURL(outfile))).default; }
const Reorder = await component('ReorderWorkspace'), Prices = await component('PriceHistory'), Editor = await component('RecordEditor'), Master = await component('MasterForm');
const button = text => [...document.querySelectorAll('button')].find(button => button.textContent.includes(text));
const Modal = ({children}) => React.createElement('section', null, children);
after(async () => { dom.window.close(); await rm(temp, { recursive: true, force: true }); });
test('low stock selection produces review data only and viewers cannot create orders', async () => {
 const root = createRoot(document.getElementById('root')); let reviewed;
 const api = async () => ({total_low_stock:1, rows:[{item_id:'i1',name:'Synthetic cable',on_hand:'2',low_stock_threshold:'5',suggested_quantity:'3',purchase_rate:'10'}]});
 await act(async () => root.render(React.createElement(Reorder,{companyId:'c1',role:'owner',api,onReview:rows=>{reviewed=rows;},onBack:()=>{}})));
 assert.equal(button('Review purchase order').disabled,true);
 await act(async () => document.querySelector('input[type=checkbox]').click());
 await act(async () => button('Review purchase order').click());
 assert.equal(reviewed[0].quantity,'3'); assert.equal(reviewed[0].item_id,'i1');
 await act(async () => root.render(React.createElement(Reorder,{companyId:'c1',role:'viewer',api,onReview:()=>assert.fail(),onBack:()=>{}})));
 assert.equal(document.querySelector('input[type=checkbox]'),null); assert.equal(button('Review purchase order'),undefined);
 await act(async () => root.unmount());
});
test('price history never applies automatically and retains inclusive tax basis on explicit apply', async () => {
 const root = createRoot(document.getElementById('root')); let applied;
 const api = async path => { assert.match(path,/parties\/p1\/item-prices\?item_id=i1&side=sales/); return {default_rate:'90',history:[{record_id:'r1',line_index:0,date:'2026-10-01',number:'INV1',quantity:'2',rate:'118',price_includes_tax:true,gst_rate:'18',discount_percent:'0'}]}; };
 await act(async () => root.render(React.createElement(Prices,{api,companyId:'c1',party:{id:'p1',name:'Synthetic'},item:{item_id:'i1',description:'Cable'},side:'sales',Modal,apply:value=>{applied=value;},close:()=>{}})));
 assert.equal(applied,undefined); await act(async () => button('Apply price').click()); assert.deepEqual(applied,{rate:'118',price_includes_tax:true}); await act(async () => root.unmount());
});
test('reorder seed is not a converted document and does not offer save-and-new', async () => {
 const root = createRoot(document.getElementById('root')); let saved;
 const api = async path => path.endsWith('bank-accounts') ? [] : {amount:'30',data:{lines:[]}};
 await act(async () => root.render(React.createElement(Editor,{features:CORE_ENHANCEMENTS,kind:'purchase_order',company:{role:'owner',tax_mode:'regular',state_code:'27'},companyId:'c1',records:[],draftSeed:{data:{lines:[{item_id:'i1',description:'Cable',quantity:'3',rate:'10',gst_rate:'0'}]}},api,Modal,labels:{purchase_order:'Purchase orders'},documentKinds:['purchase_order'],money:String,today:()=> '2026-11-02',save:value=>{saved=value;},close:()=>{}})));
 assert.equal(document.querySelector('input[name=quantity]').value,'3'); assert.equal(button('Save & new'),undefined);
 await act(async () => document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
 assert.equal(saved.kind,'purchase_order'); assert.equal(saved.data.source_document_id,undefined); assert.equal(saved.data.lines[0].item_id,'i1'); await act(async () => root.unmount());
});
test('master optional zero terms and threshold survive save rather than becoming disabled', async () => {
 const root = createRoot(document.getElementById('root')); let saved;
 await act(async () => root.render(React.createElement(Master,{features:CORE_ENHANCEMENTS,kind:'party',record:{name:'Synthetic',data:{payment_terms_days:0}},save:value=>{saved=value;},close:()=>{}})));
 await act(async () => document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
 assert.equal(saved.data.payment_terms_days,0); await act(async () => root.unmount());
 const other = createRoot(document.getElementById('root'));
 await act(async () => other.render(React.createElement(Master,{features:CORE_ENHANCEMENTS,kind:'item',record:{name:'Cable',data:{track_stock:true,low_stock_threshold:'0'}},save:value=>{saved=value;},close:()=>{}})));
 await act(async () => document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
 assert.equal(saved.data.low_stock_threshold,'0'); await act(async () => other.unmount());
});
test('payment terms preserve manual due dates until explicitly applied', async () => {
 const root = createRoot(document.getElementById('root'));
 const api = async path => path.includes('/due-date?') ? {payment_terms_days:30,suggested_due_date:'2026-12-02'} : path.endsWith('bank-accounts') ? [] : {amount:'30',data:{lines:[]}};
 await act(async () => root.render(React.createElement(Editor,{features:CORE_ENHANCEMENTS,kind:'sales_invoice',company:{role:'owner',tax_mode:'regular',state_code:'27'},companyId:'c1',records:[],source:{id:'s1',name:'Synthetic',date:'2026-11-02',data:{party_id:'p1',due_date:'2026-11-15',lines:[{description:'Cable',quantity:'1',rate:'10'}]}},edit:true,api,Modal,labels:{sales_invoice:'Sales invoices'},documentKinds:['sales_invoice'],money:String,today:()=> '2026-11-02',save:()=>{},close:()=>{}})));
 assert.equal(document.querySelector('input[name=due_date]').value,'2026-11-15');
 await act(async () => button('Apply payment terms').click()); assert.equal(document.querySelector('input[name=due_date]').value,'2026-12-02'); await act(async () => root.unmount());
});
test('master archive is reversible and delivery address is independent of billing', async () => {
 const root = createRoot(document.getElementById('root')); let saved;
 const props={features:CORE_ENHANCEMENTS,kind:'party',record:{id:'p1',name:'Synthetic',data:{address:'Billing office',shipping_address:'Delivery warehouse',is_active:true}},save:value=>{saved=value;},close:()=>{}};
 await act(async () => root.render(React.createElement(Master,props)));
 await act(async () => document.querySelector('input[type=checkbox]').click());
 await act(async () => document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
 assert.equal(saved.data.is_active,false); assert.equal(saved.data.address,'Billing office'); assert.equal(saved.data.shipping_address,'Delivery warehouse');
 await act(async () => document.querySelector('input[type=checkbox]').click());
 await act(async () => document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
 assert.equal(saved.data.is_active,true); await act(async () => root.unmount());
});
test('legacy API master form retains core editing without submitting unsupported new metadata', async () => {
 const root=createRoot(document.getElementById('root'));let saved;
 await act(async()=>root.render(React.createElement(Master,{kind:'party',record:{name:'Synthetic',data:{is_active:false,credit_limit:'100',payment_terms_days:30,shipping_address:'Separate depot',address:'Billing'}},features:[],save:value=>{saved=value;},close:()=>{}})));
 assert.equal(document.querySelector('input[name=credit_limit]'),null);assert.equal(document.querySelector('input[name=shipping_address]'),null);assert.match(document.body.textContent,/unsupported settings will not be submitted/);
 await act(async()=>document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
 assert.equal(saved.data.address,'Billing');for(const field of ['is_active','shipping_address','credit_limit','payment_terms_days'])assert.equal(Object.hasOwn(saved.data,field),false);
 await act(async()=>root.unmount());
});
test('changing item classification never silently drops an existing threshold or hides the way to clear it',async()=>{
 const root=createRoot(document.getElementById('root'));let saved;
 await act(async()=>root.render(React.createElement(Master,{features:CORE_ENHANCEMENTS,kind:'item',record:{name:'Synthetic threshold',data:{track_stock:true,item_type:'goods',low_stock_threshold:'2'}},save:value=>{saved=value;},close:()=>{}})));
 await act(async()=>{const select=document.querySelector('select[name=item_type]');select.value='services';select.dispatchEvent(new window.Event('change',{bubbles:true}));});
 const input=document.querySelector('input[name=low_stock_threshold]');assert.ok(input);assert.equal(input.value,'2');
 await act(async()=>document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));assert.equal(saved.data.low_stock_threshold,'2');
 await act(async()=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(input,'');input.dispatchEvent(new window.Event('input',{bubbles:true}));input.dispatchEvent(new window.Event('change',{bubbles:true}));});
 await act(async()=>document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));assert.equal(saved.data.low_stock_threshold,null);
 await act(async()=>root.unmount());
});
