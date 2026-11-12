import test from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,rm} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';import {build} from 'esbuild';import {JSDOM} from 'jsdom';import React,{act} from 'react';
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true});window.scrollTo=()=>{};
const {createRoot}=await import('react-dom/client');const tmp=await mkdtemp(resolve('node_modules/.accounting-safety-'));const components={};
for(const name of ['BankWorkspace','CommerceMoneyForm','Reports','ReorderWorkspace']){const outfile=resolve(tmp,name+'.mjs');await build({entryPoints:['src/'+name+'.jsx'],outfile,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react','react-dom','lucide-react']});components[name]=(await import(pathToFileURL(outfile))).default;}
const response=data=>({ok:true,json:async()=>data});const label=text=>[...document.querySelectorAll('label')].find(x=>x.textContent.trim().startsWith(text));
async function change(node,value){const proto=node.tagName==='SELECT'?window.HTMLSelectElement.prototype:window.HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(node,value);await act(async()=>node.dispatchEvent(new window.Event(node.tagName==='SELECT'?'change':'input',{bubbles:true})));}
const submit=form=>form.dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
test('bank review suppresses double submit and ignores a late result after switching bank',async()=>{
 let finish,writes=0;globalThis.fetch=async(url,options={})=>{if(options.method==='POST'){writes++;return new Promise(resolve=>{finish=resolve;});}if(url.includes('/cash-book?'))return response({opening:{cash:0,bank:0},closing:{cash:0,bank:0},rows:[]});if(url.endsWith('/bank-accounts'))return response([{id:'default',name:'Bank A'},{id:'bank-b',name:'Bank B'}]);if(url.includes('/bank-reconciliation?'))return response({});return response([]);};
 const root=createRoot(document.getElementById('root'));await act(async()=>root.render(React.createElement(components.BankWorkspace,{companyId:'c1',records:[],role:'owner'})));
 const form=[...document.querySelectorAll('form')].find(x=>x.textContent.includes('Save review'));await act(async()=>{submit(form);submit(form);});assert.equal(writes,1);
 await change(label('Active bank').querySelector('select'),'bank-b');await act(async()=>finish(response({id:'review-a',as_of:'2026-11-01',note:'BANK A PRIVATE REVIEW'})));assert.doesNotMatch(document.body.textContent,/BANK A PRIVATE REVIEW/);await act(async()=>root.unmount());
});
for (const outcome of ['success','failure']) test(`bank unmatch suppresses duplicate clicks and ignores late ${outcome} after bank switch`,async()=>{
 let finish,writes=0,reads=0;globalThis.fetch=async(url,options={})=>{if(options.method==='DELETE'){writes++;return new Promise(resolve=>{finish=resolve;});}if(url.includes('/cash-book?'))return response({opening:{cash:0,bank:0},closing:{cash:0,bank:0},rows:[]});if(url.endsWith('/bank-accounts'))return response([{id:'default',name:'Bank A'},{id:'bank-b',name:'Bank B'}]);if(url.includes('/bank-statement?')){reads++;return response(url.includes('bank-b')?[]:[{id:'line-a',date:'2026-04-01',description:'A matched row',amount:'100',matched_record_id:'invoice-a'}]);}if(url.includes('/bank-reconciliation?'))return response({});return response([]);};
 const root=createRoot(document.getElementById('root'));await act(async()=>root.render(React.createElement(components.BankWorkspace,{companyId:'c1',records:[],role:'owner'})));
 const button=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('Matched · Unmatch'));assert.ok(button);
 await act(async()=>{button.click();button.click();});assert.equal(writes,1);assert.equal(button.disabled,true);
 await change(label('Active bank').querySelector('select'),'bank-b');const before=reads;
 await act(async()=>finish(outcome==='success'?response({}):{ok:false,status:409,json:async()=>({detail:'BANK A DELETE FAILED'})}));assert.equal(reads,before);assert.doesNotMatch(document.body.textContent,/BANK A DELETE FAILED|A matched row/);await act(async()=>root.unmount());
});
test('commerce credit change removes hidden quantities from submitted payload',async()=>{
 let sent;const workspace={connection:{status:'active',config:{}},orders:[{external_id:'order',number:'Order'}],stock:[],links:['A','B'].map(id=>({entity_type:'credit',external_id:id,snapshot:{order_id:'order',lines:[{product_id:id,quantity:'5'}]}}))};
 const root=createRoot(document.getElementById('root'));await act(async()=>root.render(React.createElement(components.CommerceMoneyForm,{workspace,banks:[],send:async(op,body)=>{sent=body;},onDone:()=>{}})));
 await change(label('Action').querySelector('select'),'receipt');await change(label('Store order').querySelector('select'),'order');await change(label('Financial credit note').querySelector('select'),'A');await change(label('A · credited').querySelector('input'),'2');await change(label('Financial credit note').querySelector('select'),'B');await change(label('B · credited').querySelector('input'),'1');await act(async()=>submit(document.querySelector('form')));assert.deepEqual(sent.data.lines,[{product_id:'B',quantity:'1'}]);assert.equal(sent.data.credit_id,'B');await act(async()=>root.unmount());
});
test('GST transitions restore ordinary dates and company changes clear party requests',async()=>{
 const urls=[];globalThis.fetch=url=>{urls.push(url);return new Promise(()=>{});};const root=createRoot(document.getElementById('root'));const render=companyId=>root.render(React.createElement(components.Reports,{companyId,records:[{kind:'party',name:companyId==='a'?'Alice':'Bob'}]}));await act(async()=>render('a'));
 await act(async()=>[...document.querySelectorAll('button')].find(x=>x.textContent.includes('Sales register')).click());const start=document.querySelector('[aria-label="From date"]').value,end=document.querySelector('[aria-label="To date"]').value;
 await change(label('Report').querySelector('select'),'gstr1');await change(label('Return frequency').querySelector('select'),'quarter');assert.match(urls.at(-1),/gst-returns/);await change(label('Report').querySelector('select'),'sales');assert.equal(document.querySelector('[aria-label="From date"]').value,start);assert.equal(document.querySelector('[aria-label="To date"]').value,end);
 await change(label('Report').querySelector('select'),'parties');await change(label('Party').querySelector('select'),'Alice');assert.match(urls.at(-1),/party=Alice/);await act(async()=>render('b'));assert.match(urls.at(-1),/\/companies\/b\//);assert.doesNotMatch(urls.at(-1),/Alice/);assert.equal(label('Party').querySelector('select').value,'');await act(async()=>root.unmount());
});
test('reorder keeps saved purchase-order confirmation across refresh and scopes it to its company',async()=>{
 const root=createRoot(document.getElementById('root'));let opened,reads=0;
 const order={companyId:'a',id:'po-1',kind:'purchase_order',number:'PO-007',name:'Supplier'};
 const api=async()=>{reads++;return {total_low_stock:1,rows:[{item_id:'item',name:'Synthetic goods',on_hand:'5',low_stock_threshold:'12',suggested_quantity:'7'}]};};
 const render=companyId=>root.render(React.createElement(components.ReorderWorkspace,{companyId,role:'owner',api,createdOrder:order,onOpenOrder:value=>{opened=value;},onReview:()=>{},onBack:()=>{}}));
 await act(async()=>render('a'));assert.match(document.body.textContent,/Purchase order PO-007 created/);assert.match(document.body.textContent,/Synthetic goods/);
 await act(async()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='Open purchase order PO-007').click());assert.equal(opened.id,'po-1');
 await act(async()=>[...document.querySelectorAll('button')].find(x=>x.textContent==='Refresh').click());assert.equal(reads,2);assert.match(document.body.textContent,/Purchase order PO-007 created/);assert.match(document.body.textContent,/Synthetic goods/);
 await act(async()=>render('b'));assert.doesNotMatch(document.body.textContent,/PO-007/);await act(async()=>root.unmount());
});
test.after(async()=>{dom.window.close();await rm(tmp,{recursive:true,force:true});});
