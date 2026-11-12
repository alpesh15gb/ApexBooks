import test,{after} from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,rm} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';import {build} from 'esbuild';import {JSDOM} from 'jsdom';import React,{act} from 'react';
const temp=await mkdtemp(resolve('node_modules/.discount-tests-'));await build({entryPoints:['src/RecordEditor.jsx'],outfile:resolve(temp,'editor.mjs'),bundle:true,platform:'node',format:'esm',external:['react','react-dom','lucide-react']});
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});Object.assign(globalThis,{window:dom.window,document:dom.window.document,IS_REACT_ACT_ENVIRONMENT:true});const {createRoot}=await import('react-dom/client');const Editor=(await import(pathToFileURL(resolve(temp,'editor.mjs')))).default;
after(async()=>{dom.window.close();await rm(temp,{recursive:true,force:true});});
const Modal=({children})=>React.createElement('section',null,children);
const line={description:'Synthetic service',quantity:'1',rate:'100',discount_amount:'10',discount_percent:'0',gst_rate:'0',tax_treatment:'nil_rated'};
const company={role:'owner',tax_mode:'regular',state_code:'27',name:'Synthetic Books'};
async function change(selector,value){await act(async()=>{const el=document.querySelector(selector);const proto=el.tagName==='SELECT'?window.HTMLSelectElement.prototype:el.tagName==='TEXTAREA'?window.HTMLTextAreaElement.prototype:window.HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(el,value);el.dispatchEvent(new window.Event(el.tagName==='SELECT'?'change':'input',{bubbles:true}));});}
async function mount(extra={}){let saved;const root=createRoot(document.getElementById('root'));await act(async()=>root.render(React.createElement(Editor,{kind:'sales_invoice',company,companyId:'c1',records:[],source:{id:'r1',name:'Buyer',date:'2026-11-02',data:{version:0,lines:[line]}},edit:true,api:async path=>path.endsWith('bank-accounts')?[]:{amount:'90',data:{lines:[]}},Modal,labels:{sales_invoice:'Sales invoices'},documentKinds:['sales_invoice','credit_note'],money:String,today:()=> '2026-11-02',save:payload=>{saved=payload;},close:()=>{},...extra})));return{root,get saved(){return saved;}};}
const submit=()=>act(async()=>document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})));
test('reopened fixed discount remains visible and a nonfinancial edit preserves exact input',async()=>{
 const view=await mount();assert.equal(document.querySelector('[name=discount_mode]').value,'amount');assert.equal(document.querySelector('[name=discount_amount]').value,'10');
 await change('details.document-notes textarea','Reviewed header only');await submit();assert.equal(view.saved.data.lines[0].discount_amount,'10');assert.equal(Object.hasOwn(view.saved.data.lines[0],'discount_percent'),false);assert.equal(view.saved.data.lines[0].rate,'100');await act(async()=>view.root.unmount());
});
test('switching percent and rupee modes cannot submit both inputs',async()=>{
 const view=await mount();await change('[name=discount_mode]','percent');assert.equal(document.querySelector('[name=discount_amount]'),null);await change('[name=discount_percent]','5');await submit();assert.equal(view.saved.data.lines[0].discount_percent,'5');assert.equal(Object.hasOwn(view.saved.data.lines[0],'discount_amount'),false);await act(async()=>view.root.unmount());
});
test('linked return retains fixed amount and requires review again after quantity changes',async()=>{
 const view=await mount({kind:'credit_note',edit:false,source:undefined,relatedSource:{id:'r1',name:'Buyer',data:{lines:[{...line,quantity:'2'}]}},labels:{credit_note:'Credit notes'}});
 assert.equal(document.querySelector('[name=discount_amount]').value,'10');await submit();assert.equal(view.saved,undefined);assert.match(document.body.textContent,/Review the fixed discounts/);
 const ack=()=>[...document.querySelectorAll('label')].find(label=>label.textContent.includes('I reviewed the copied')).querySelector('input');await act(async()=>ack().click());await change('[name=quantity]','1');assert.equal(ack().checked,false);assert.equal(document.querySelector('[name=discount_amount]').value,'10');await act(async()=>ack().click());await submit();assert.equal(view.saved.data.lines[0].discount_amount,'10');await act(async()=>view.root.unmount());
});
test('conversion keeps fixed/inclusive/document discount inputs unchanged without mandatory return acknowledgement',async()=>{
 const original={id:'quote1',name:'Buyer',data:{document_discount_percent:'10',lines:[{...line,rate:'118',gst_rate:'18',tax_treatment:'taxable',price_includes_tax:true}]}};
 const view=await mount({edit:false,source:original});
 assert.match(document.body.textContent,/not automatically prorated/);assert.doesNotMatch(document.body.textContent,/I reviewed the copied/);
 await submit();assert.equal(view.saved.data.document_discount_percent,'10');assert.equal(view.saved.data.lines[0].discount_amount,'10');assert.equal(view.saved.data.lines[0].price_includes_tax,true);assert.equal(view.saved.data.source_document_id,'quote1');await act(async()=>view.root.unmount());
});
test('manual source selection and contextual return copy identical fixed plus document discount inputs',async()=>{
 const source={id:'invoice-discount',kind:'sales_invoice',posted:true,name:'Buyer',number:'INV1',data:{document_discount_percent:'10',place_of_supply:'27',lines:[line]}};
 const outputs=[];
 for(const contextual of [false,true]){
  const view=await mount({kind:'credit_note',edit:false,source:undefined,relatedSource:contextual?source:undefined,records:[source],labels:{credit_note:'Credit notes'},api:async path=>path.endsWith('bank-accounts')?[]:path.endsWith('/records/invoice-discount')?source:{amount:'81',data:{lines:[]}}});
  if(!contextual)await change('.source-document select','invoice-discount');
  const ack=[...document.querySelectorAll('label')].find(label=>label.textContent.includes('I reviewed the copied')).querySelector('input');await act(async()=>ack.click());await submit();
  assert.equal(view.saved.data.document_discount_percent,'10');assert.equal(view.saved.data.lines[0].discount_amount,'10');assert.equal(Object.hasOwn(view.saved.data.lines[0],'discount_percent'),false);outputs.push(view.saved.data);await act(async()=>view.root.unmount());
 }
 for(const data of outputs){assert.equal(data.applied_to,source.id);assert.equal(data.lines[0].quantity,'1');assert.equal(data.lines[0].rate,'100');}
});

test('reopening financial-only credit and debit notes preserves false stock-return flag',async()=>{
 for(const kind of ['credit_note','debit_note']){
  const source={id:'note',kind,name:'Buyer',number:'NOTE-1',date:'2026-11-02',data:{version:0,return_stock:false,applied_to:'original',lines:[line]}};
  const view=await mount({kind,source,records:[{id:'original',kind:kind==='credit_note'?'sales_invoice':'purchase_bill',posted:true,name:'Buyer',amount:100,data:{lines:[line]}}],documentKinds:['sales_invoice','purchase_bill','credit_note','debit_note']});
  await submit();assert.equal(view.saved.data.return_stock,false);await act(async()=>view.root.unmount());
 }
});

test('quick-add item freezes line removal, submit and close until its request resolves',async()=>{
 let finish,writes=0,closed=0;
 const source={id:'r1',name:'Buyer',date:'2026-11-02',data:{lines:[{...line,description:'Item A'},{...line,description:'Item B',quantity:'3'}]}};
 const view=await mount({source,close:()=>{closed++;},api:async(path,options={})=>{if(options.method==='POST'&&path.endsWith('/records')){writes++;return new Promise(resolve=>{finish=resolve;});}return path.endsWith('bank-accounts')?[]:{amount:'90',data:{lines:[]}};}});
 const add=[...document.querySelectorAll('button')].find(x=>x.textContent==='Save as item');
 await act(async()=>{add.click();add.click();});assert.equal(writes,1);
 const remove=document.querySelector('[aria-label="Remove item 1"]');assert.equal(remove.matches(':disabled'),true);
 await act(async()=>remove.click());await submit();assert.equal(view.saved,undefined);
 await act(async()=>window.dispatchEvent(new window.Event('apex-close-editor')));assert.equal(closed,0);
 await act(async()=>finish({id:'master-a',name:'Item A',kind:'item',data:{}}));await submit();
 assert.equal(view.saved.data.lines.length,2);assert.equal(view.saved.data.lines[0].item_id,'master-a');assert.equal(view.saved.data.lines[1].description,'Item B');assert.equal(view.saved.data.lines[1].quantity,'3');await act(async()=>view.root.unmount());
});
test('quick-add party cannot replace an edited name or submit while pending',async()=>{
 let finish;const view=await mount({api:async(path,options={})=>options.method==='POST'&&path.endsWith('/records')?new Promise(resolve=>{finish=resolve;}):path.endsWith('bank-accounts')?[]:{amount:'90',data:{lines:[]}}});
 const add=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('as a new customer'));await act(async()=>add.click());
 assert.equal(document.querySelector('input[name="name"]').matches(':disabled'),true);await change('input[name="name"]','Different buyer');await submit();assert.equal(view.saved,undefined);
 await act(async()=>finish({id:'party-buyer',name:'Buyer',kind:'party',data:{}}));await submit();assert.equal(view.saved.name,'Buyer');assert.equal(view.saved.data.party_id,'party-buyer');await act(async()=>view.root.unmount());
});

test('linked debit-note preview includes the source bill required for inherited ITC',async()=>{
 let preview;
 const source={id:'note',kind:'debit_note',name:'Supplier',number:'DN-1',date:'2026-11-02',data:{applied_to:'source-bill',lines:[line]}};
 const view=await mount({kind:'debit_note',source,documentKinds:['debit_note'],api:async(path,options={})=>{if(path.endsWith('/documents/preview'))preview=JSON.parse(options.body);return path.endsWith('bank-accounts')?[]:{amount:'90',data:{lines:[]}};}});
 await act(async()=>new Promise(resolve=>setTimeout(resolve,400)));
 assert.equal(preview.data.applied_to,'source-bill');
 await act(async()=>view.root.unmount());
});

test('duplicate purchase descriptions select distinct source lines and preserve the reference on reopen',async()=>{
 const original={id:'bill-ref',kind:'purchase_bill',posted:true,name:'Supplier',data:{lines:[0,1].map(i=>({description:'Same service',quantity:'2',rate:'100',gst_rate:'18',tax_treatment:'taxable',itc_treatment:i?'pending_review':'ineligible',source_line_id:`${i}:fingerprint`,source_document_id:'bill-ref',source_line_number:i+1,remaining_return_quantity:i?null:'0'}))}};
 const api=async path=>path.includes('/records/')?original:path.endsWith('bank-accounts')?[]:{amount:'118',data:{lines:[]}};
 const view=await mount({kind:'debit_note',documentKinds:['debit_note'],edit:false,source:undefined,relatedSource:original,api,labels:{debit_note:'Debit notes'}});
 assert.equal(document.querySelector('[aria-label="Item 1 source purchase line"]').value,'0:fingerprint');
 assert.equal(document.querySelector('[aria-label="Item 1 source purchase line"] option[value=""]'),null);
 const choiceText=document.querySelector('[aria-label="Item 1 source purchase line"]').textContent;assert.match(choiceText,/additional return qty 0/);assert.match(choiceText,/additional return qty needs review/);
 await act(async()=>document.querySelector('[aria-label="Remove item 2"]').click());
 await change('[aria-label="Item 1 source purchase line"]','1:fingerprint');await change('[name=quantity]','1');await submit();
 assert.equal(view.saved.data.lines.length,1);assert.equal(view.saved.data.lines[0].source_line_id,'1:fingerprint');assert.equal(view.saved.data.lines[0].source_document_id,'bill-ref');assert.equal(view.saved.data.lines[0].itc_treatment,'pending_review');
 const saved=view.saved;await act(async()=>view.root.unmount());
 const reopened=await mount({kind:'debit_note',documentKinds:['debit_note'],edit:true,source:{...saved,id:'note-ref'},api,labels:{debit_note:'Debit notes'}});await submit();assert.equal(reopened.saved.data.lines[0].source_line_id,'1:fingerprint');assert.equal(reopened.saved.data.lines[0].quantity,'1');await act(async()=>reopened.root.unmount());
});

test('source-option load failure and retry preserve the edited return draft',async()=>{
 let fail=true;const sourceLine={description:'Saved service',quantity:'2',rate:'100',gst_rate:'18',source_line_id:'0:saved',source_document_id:'bill',source_line_number:1,itc_treatment:'ineligible'};
 const api=async path=>{if(path.includes('/records/')){if(fail)throw Error('Unavailable');return{id:'bill',data:{lines:[sourceLine]}};}return path.endsWith('bank-accounts')?[]:{amount:'118',data:{lines:[]}};};
 const view=await mount({kind:'debit_note',documentKinds:['debit_note'],source:{id:'note',name:'Supplier',date:'2026-11-02',data:{applied_to:'bill',lines:[sourceLine]}},api,labels:{debit_note:'Debit notes'}});
 assert.match(document.body.textContent,/Source lines could not be loaded/);await change('[name=quantity]','1');fail=false;
 await act(async()=>[...document.querySelectorAll('button')].find(button=>button.textContent==='Retry source lines').click());
 assert.equal(document.querySelector('[name=quantity]').value,'1');assert.equal(document.querySelector('[aria-label="Item 1 source purchase line"]').value,'0:saved');await submit();assert.equal(view.saved.data.lines[0].source_line_id,'0:saved');assert.equal(view.saved.data.lines[0].quantity,'1');await act(async()=>view.root.unmount());
});

test('debit-note amendment preview identifies the edited note without sending preview context to save',async()=>{
 const calls=[];const note={id:'note-context',name:'Supplier',date:'2026-11-02',data:{applied_to:'bill-context',lines:[{description:'Service',quantity:'1',rate:'100',gst_rate:'18'}]}};
 const api=async(path,options)=>{if(path.endsWith('/documents/preview'))calls.push(JSON.parse(options.body));return path.endsWith('/bank-accounts')?[]:path.includes('/records/')?{data:{lines:[]}}:{amount:'118',data:{lines:[]}};};
 const view=await mount({kind:'debit_note',documentKinds:['debit_note'],source:note,api,labels:{debit_note:'Debit notes'}});await act(async()=>new Promise(resolve=>setTimeout(resolve,400)));
 assert.equal(calls.at(-1).data.editing_record_id,'note-context');await submit();assert.equal(view.saved.data.editing_record_id,undefined);await act(async()=>view.root.unmount());
});
