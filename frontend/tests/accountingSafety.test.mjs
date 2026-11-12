import test from 'node:test';import assert from 'node:assert/strict';import {mkdtemp,rm} from 'node:fs/promises';import {resolve} from 'node:path';import {pathToFileURL} from 'node:url';import {build} from 'esbuild';import {JSDOM} from 'jsdom';import React,{act} from 'react';
const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'});Object.assign(globalThis,{window:dom.window,document:dom.window.document,localStorage:dom.window.localStorage,IS_REACT_ACT_ENVIRONMENT:true});window.scrollTo=()=>{};
const {createRoot}=await import('react-dom/client');const tmp=await mkdtemp(resolve('node_modules/.accounting-safety-'));const components={};
for(const name of ['BankWorkspace','CommerceWorkspace','CommerceMoneyForm','Reports','ReorderWorkspace','DayBook']){const outfile=resolve(tmp,name+'.mjs');await build({entryPoints:['src/'+name+'.jsx'],outfile,bundle:true,platform:'node',format:'esm',jsx:'automatic',external:['react','react-dom','lucide-react']});components[name]=(await import(pathToFileURL(outfile))).default;}
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
test('noncash Day book journal exposes debit and credit totals without inventing money movement',async()=>{
 const root=createRoot(document.getElementById('root'));
 const api=async()=>({count:1,totals:{sales:'0',purchases:'0',expenses:'0',money_in:'0',money_out:'0',net:'0'},rows:[{id:'j',kind:'journal',number:'MANUAL-100',name:'Noncash correction',amount:'100',debit_total:'100',credit_total:'100',posted:true,money_in:'0',money_out:'0'}]});
 await act(async()=>root.render(React.createElement(components.DayBook,{companyId:'a',records:[],api,labels:{},onOpen:()=>{}})));
 const row=document.querySelector('tbody tr');assert.match(row.textContent,/Noncash correction/);assert.match(row.textContent,/Debit ₹100.00 · Credit ₹100.00/);
 assert.equal(row.children[3].textContent,'');assert.equal(row.children[4].textContent,'');await act(async()=>root.unmount());
});
test('item activity and party statements explain their quantity and opening-balance basis',async()=>{
 globalThis.fetch=async()=>response({rows:[{id:'doc',kind:'sales_invoice',name:'Synthetic movement',hsn:'',opening_quantity:'0',purchased_quantity:'7',sold_quantity:'1',closing_quantity:'6',sales_value:'80'}],opening_receivable:'1500',opening_payable:'0',closing_receivable:'1500',closing_payable:'0'});
 const root=createRoot(document.getElementById('root'));await act(async()=>root.render(React.createElement(components.Reports,{companyId:'a',records:[]})));
 await act(async()=>[...document.querySelectorAll('button')].find(x=>x.textContent.includes('Sales register')).click());
 await change(label('Report').querySelector('select'),'items');
 assert.match(document.body.textContent,/NET THROUGH END DATE/);assert.match(document.body.textContent,/not stock on hand/);assert.doesNotMatch(document.querySelector('thead').textContent,/CLOSING|OPENING/);
 await change(label('Report').querySelector('select'),'parties');assert.match(document.body.textContent,/Posted opening balances and settlements are included/);assert.doesNotMatch(document.body.textContent,/until linked/);
 await act(async()=>root.unmount());
});
test.after(async()=>{dom.window.close();await rm(tmp,{recursive:true,force:true});});
test('commerce money submission is single-flight, freezes fields, and suppresses completion after close',async()=>{
 const root=createRoot(document.getElementById('root'));let finish,writes=0,done=0;
 const workspace={connection:{id:'connection-a',status:'active',config:{}},links:[],orders:[],stock:[]};
 await act(async()=>root.render(React.createElement(components.CommerceMoneyForm,{workspace,banks:[],busy:false,send:()=>{writes++;return new Promise(resolve=>{finish=resolve;});},onDone:()=>done++})));
 await act(async()=>{submit(document.querySelector('form'));submit(document.querySelector('form'));});assert.equal(writes,1);assert.equal(document.querySelector('fieldset').disabled,true);
 await act(async()=>root.unmount());await act(async()=>finish());assert.equal(done,0);
});
test('commerce money completion does not refresh an old store after switching connection',async()=>{
 const root=createRoot(document.getElementById('root'));let finish;const urls=[];
 const connections=['a','b'].map(id=>({id,name:id,channel:'synthetic'}));
 const api=async(path,options={})=>{urls.push(path);if(options.method==='POST')return new Promise(resolve=>{finish=resolve;});if(path.endsWith('/bank-accounts'))return [];if(path.endsWith('/connections'))return connections;const id=path.includes('/b/')?'b':'a';return {connection:{id,status:'active',base_url:`https://${id}.invalid`,config:{}},orders:[],stock:[],links:[],outbox:[],reconciliations:[],summary:{}};};
 await act(async()=>root.render(React.createElement(components.CommerceWorkspace,{company:{id:'c',name:'Synthetic',role:'editor'},records:[],api})));
 await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='payments').click());await act(async()=>submit(document.querySelector('form')));
 await change(label('Store channel').querySelector('select'),'b');const oldReads=urls.filter(p=>p.endsWith('/a/workspace')).length;
 await act(async()=>finish({queued:true}));assert.equal(urls.filter(p=>p.endsWith('/a/workspace')).length,oldReads);assert.match(document.body.textContent,/https:\/\/b.invalid/);assert.doesNotMatch(document.body.textContent,/Source transaction queued/);
 await act(async()=>root.unmount());
});
test('commerce money failure preserves input and unlocks explicit retry',async()=>{
 const root=createRoot(document.getElementById('root'));let reject,writes=0,done=0;
 const workspace={connection:{id:'a',status:'active',config:{}},links:[],orders:[],stock:[]};
 await act(async()=>root.render(React.createElement(components.CommerceMoneyForm,{workspace,banks:[],send:()=>{writes++;return writes===1?new Promise((resolve,fail)=>{reject=fail;}):Promise.resolve();},onDone:()=>done++})));
 await change(label('Bank / provider').querySelector('input'),'SYNTHETIC-REF');await act(async()=>submit(document.querySelector('form')));await act(async()=>reject(Object.assign(Error('Synthetic validation failure'),{status:422})));
 assert.equal(document.querySelector('fieldset').disabled,false);assert.equal(label('Bank / provider').querySelector('input').value,'SYNTHETIC-REF');assert.match(document.querySelector('[role=alert]').textContent,/Synthetic validation/);
 await act(async()=>submit(document.querySelector('form')));assert.equal(writes,2);assert.equal(done,1);await act(async()=>root.unmount());
});
test('accepted commerce command remains successful when only its follow-up refresh fails',async(t)=>{
 const root=createRoot(document.getElementById('root'));t.after(async()=>{await act(async()=>root.unmount());});let writes=0,reads=0;
 const workspace={connection:{id:'a',status:'active',base_url:'https://synthetic.invalid',config:{}},orders:[],stock:[],links:[],outbox:[],reconciliations:[],summary:{}};
 const api=async(path,options={})=>{if(options.method==='POST'){writes++;return {id:'queued-command',status:'pending'};}if(path.endsWith('/bank-accounts'))return [];if(path.endsWith('/connections'))return [{id:'a',name:'Synthetic',channel:'test'}];reads++;if(reads===2)throw Error('Synthetic refresh failure');return workspace;};
 await act(async()=>root.render(React.createElement(components.CommerceWorkspace,{company:{id:'c',name:'Synthetic',role:'editor'},records:[],api})));
 await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='payments').click());await change(label('Bank / provider').querySelector('input'),'ACCEPTED-REF');await act(async()=>submit(document.querySelector('form')));
 assert.equal(writes,1);assert.equal(label('Bank / provider').querySelector('input').value,'');assert.match(document.body.textContent,/queued/i);assert.match(document.querySelector('[role=alert]').textContent,/Do not queue it again/);
 await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Refresh').click());assert.equal(writes,1);assert.equal(reads,3);await act(async()=>root.unmount());
});
for(const status of [0,408,409,503])test(`uncertain commerce ${status} retries frozen payload after attempted edit`,async(t)=>{
 const root=createRoot(document.getElementById('root'));t.after(async()=>act(async()=>root.unmount()));const sent=[];const workspace={connection:{id:'a',status:'active',config:{}},links:[],orders:[],stock:[]};
 await act(async()=>root.render(React.createElement(components.CommerceMoneyForm,{workspace,banks:[],send:async(op,payload)=>{sent.push({op,payload});if(sent.length===1)throw Object.assign(Error('Uncertain synthetic response'),{status});},onDone:()=>{}})));
 await change(label('Bank / provider').querySelector('input'),'ORIGINAL-REF');await change(label('Amount').querySelector('input'),'100');await act(async()=>submit(document.querySelector('form')));
 assert.equal(document.querySelector('fieldset').disabled,true);assert.match(document.querySelector('[role=status]').textContent,/ORIGINAL-REF/);
 await change(label('Bank / provider').querySelector('input'),'EDITED-REF');await change(label('Amount').querySelector('input'),'200');await act(async()=>submit(document.querySelector('form')));
 assert.deepEqual(sent[1],sent[0]);assert.equal(document.querySelector('fieldset').disabled,false);assert.match(document.querySelector('[role=status]').textContent,/accepted/);
});
test('uncertain commerce command survives store switch with the same command ID and payload',async(t)=>{
 const root=createRoot(document.getElementById('root'));t.after(async()=>act(async()=>root.unmount()));const commands=[];
 const api=async(path,options={})=>{if(options.method==='POST'){commands.push({path,body:JSON.parse(options.body)});if(commands.length===1)throw Object.assign(Error('Synthetic lost response'),{status:0});return {status:'pending'};}if(path.endsWith('/bank-accounts'))return [];if(path.endsWith('/connections'))return ['a','b'].map(id=>({id,name:id,channel:'test'}));const id=path.includes('/b/')?'b':'a';return {connection:{id,status:'active',config:{}},orders:[],stock:[],links:[],outbox:[],reconciliations:[],summary:{}};};
 await act(async()=>root.render(React.createElement(components.CommerceWorkspace,{company:{id:'c',name:'Synthetic',role:'editor'},records:[],api})));
 await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='payments').click());await change(label('Bank / provider').querySelector('input'),'RECOVER-A');await act(async()=>submit(document.querySelector('form')));
 await change(label('Store channel').querySelector('select'),'b');assert.doesNotMatch(document.body.textContent,/RECOVER-A/);
 await change(label('Store channel').querySelector('select'),'a');assert.match(document.body.textContent,/RECOVER-A/);assert.equal(document.querySelector('fieldset').disabled,true);
 await act(async()=>submit(document.querySelector('form')));assert.equal(commands.length,2);assert.deepEqual(commands[1],commands[0]);
});
for(const outcome of ['success','unknown','definitive'])test(`commerce shared recovery observes ${outcome} after remount before response`,async(t)=>{
 const root=createRoot(document.getElementById('root'));t.after(async()=>act(async()=>root.unmount()));const commands=[];let finish,fail;
 const workspace={connection:{id:'a',status:'active',config:{}},orders:[],stock:[],links:[],outbox:[],reconciliations:[],summary:{}};
 const api=async(path,options={})=>{if(options.method==='POST'){commands.push(JSON.parse(options.body));if(commands.length===1)return new Promise((resolve,reject)=>{finish=resolve;fail=reject;});return {status:'pending'};}if(path.endsWith('/bank-accounts'))return [];if(path.endsWith('/connections'))return [{id:'a',name:'Synthetic',channel:'test'}];return workspace;};
 await act(async()=>root.render(React.createElement(components.CommerceWorkspace,{company:{id:'c',name:'Synthetic',role:'editor'},records:[],api})));
 const tab=name=>[...document.querySelectorAll('.commerce-tabs button')].find(b=>b.textContent===name);
 await act(async()=>tab('payments').click());await change(label('Bank / provider').querySelector('input'),'REMOUNT-ORIGINAL');await act(async()=>submit(document.querySelector('form')));
 await act(async()=>tab('overview').click());assert.match(document.body.textContent,/Reloading, signing out or leaving Ecommerce clears local recovery/);assert.match(document.body.textContent,/REMOUNT-ORIGINAL/);await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Review original money command').click());assert.equal(document.querySelector('fieldset').disabled,true);await act(async()=>submit(document.querySelector('form')));assert.equal(commands.length,1);
 await act(async()=>outcome==='success'?finish({status:'pending'}):fail(Object.assign(Error('Synthetic outcome'),{status:outcome==='unknown'?0:422})));
 await act(async()=>tab('overview').click());assert.equal(Boolean([...document.querySelectorAll('button')].find(b=>b.textContent==='Review original money command')),outcome==='unknown');if(outcome==='unknown')assert.match(document.body.textContent,/response is uncertain/);await act(async()=>tab('payments').click());
 if(outcome==='success'){assert.equal(document.querySelector('fieldset').disabled,false);assert.match(document.body.textContent,/original source command was accepted/);assert.doesNotMatch(document.body.textContent,/Retry original source command/);}
 else if(outcome==='unknown'){assert.equal(document.querySelector('fieldset').disabled,true);assert.match(document.body.textContent,/REMOUNT-ORIGINAL/);await act(async()=>submit(document.querySelector('form')));assert.equal(commands.length,2);assert.deepEqual(commands[1],commands[0]);assert.equal(document.querySelector('fieldset').disabled,false);}
 else {assert.equal(document.querySelector('fieldset').disabled,false);assert.match(document.querySelector('[role=alert]').textContent,/Synthetic outcome/);assert.doesNotMatch(document.body.textContent,/Retry original source command/);}
});
for(const outcome of ['success','failure'])test(`commerce ignores obsolete company connection ${outcome} even when transport ignores abort`,async(t)=>{
 const root=createRoot(document.getElementById('root'));t.after(async()=>act(async()=>root.unmount()));let finish,fail;
 const api=async(path)=>{if(path.endsWith('/bank-accounts'))return [];if(path==='/companies/a/commerce/connections')return new Promise((resolve,reject)=>{finish=resolve;fail=reject;});if(path.endsWith('/connections'))return [{id:'b-store',name:'CURRENT STORE',channel:'test'}];return {connection:{id:'b-store',status:'active',config:{}},orders:[],stock:[],links:[],outbox:[],reconciliations:[],summary:{}};};
 const render=id=>root.render(React.createElement(components.CommerceWorkspace,{company:{id,name:id,role:'editor'},records:[],api}));await act(async()=>render('a'));await act(async()=>render('b'));
 await act(async()=>outcome==='success'?finish([{id:'old-store',name:'OBSOLETE PRIVATE STORE',channel:'test'}]):fail(Error('OBSOLETE PRIVATE ERROR')));
 assert.match(document.body.textContent,/CURRENT STORE/);assert.doesNotMatch(document.body.textContent,/OBSOLETE PRIVATE/);
});
for(const outcome of ['success','failure'])test(`commerce ignores obsolete store workspace ${outcome}`,async(t)=>{
 const root=createRoot(document.getElementById('root'));t.after(async()=>act(async()=>root.unmount()));let finish,fail;
 const view=id=>({connection:{id,status:'active',config:{}},orders:[],stock:[],links:[],outbox:[],reconciliations:[],summary:{}});
 const api=async(path)=>{if(path.endsWith('/bank-accounts'))return [];if(path.endsWith('/connections'))return ['a','b'].map(id=>({id,name:id,channel:'test'}));if(path.includes('/a/workspace'))return new Promise((resolve,reject)=>{finish=resolve;fail=reject;});return view('b');};
 await act(async()=>root.render(React.createElement(components.CommerceWorkspace,{company:{id:'c',name:'Synthetic',role:'editor'},records:[],api})));
 await change(label('Store channel').querySelector('select'),'b');await act(async()=>outcome==='success'?finish(view('a')):fail(Error('OBSOLETE STORE ERROR')));
 assert.equal(label('Store channel').querySelector('select').value,'b');assert.doesNotMatch(document.body.textContent,/OBSOLETE STORE ERROR/);assert.ok(document.querySelector('.commerce-tabs'));
});
for(const outcome of ['success','failure'])test(`commerce mutation ignores late ${outcome} after company switch and prevents duplicate dispatch`,async(t)=>{
 const root=createRoot(document.getElementById('root'));t.after(async()=>act(async()=>root.unmount()));let finish,fail;const writes=[],reads=[];
 const api=async(path,options={})=>{if(options.method==='POST'){writes.push(path);return new Promise((resolve,reject)=>{finish=resolve;fail=reject;});}if(path.endsWith('/bank-accounts'))return [];if(path.endsWith('/connections'))return [{id:'store',name:'Store',channel:'test'}];reads.push(path);return {connection:{id:'store',status:'active',config:{}},orders:[],stock:[],links:[],outbox:[],reconciliations:[],summary:{}};};
 const render=id=>root.render(React.createElement(components.CommerceWorkspace,{company:{id,name:id,role:'editor'},records:[],api}));await act(async()=>render('a'));
 const button=[...document.querySelectorAll('button')].find(b=>b.textContent==='Scan store history');await act(async()=>{button.click();button.click();});assert.equal(writes.length,1);
 await act(async()=>render('b'));const before=reads.length;await act(async()=>outcome==='success'?finish({status:'pending'}):fail(Error('PRIVATE OLD MUTATION ERROR')));
 assert.equal(reads.length,before);assert.doesNotMatch(document.body.textContent,/History repair queued|PRIVATE OLD MUTATION ERROR/);assert.equal([...document.querySelectorAll('button')].find(b=>b.textContent==='Scan store history').disabled,false);
});
test('commerce connection creation does not expose late setup in another company',async(t)=>{
 const root=createRoot(document.getElementById('root'));t.after(async()=>act(async()=>root.unmount()));let finish;
 const api=async(path,options={})=>{if(options.method==='POST')return new Promise(resolve=>{finish=resolve;});if(path.endsWith('/bank-accounts'))return [];if(path.endsWith('/connections'))return [];throw Error('Unexpected read '+path);};
 const render=id=>root.render(React.createElement(components.CommerceWorkspace,{company:{id,name:id,role:'owner'},records:[],api}));await act(async()=>render('a'));await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Connect Bagisto').click());await act(async()=>submit(document.querySelector('form')));await act(async()=>render('b'));
 await act(async()=>finish({id:'old-store',name:'OLD PRIVATE STORE',channel:'test',setup_secret:'SYNTHETIC-ONLY-OLD-SECRET'}));assert.doesNotMatch(document.body.textContent,/OLD PRIVATE STORE|Server bridge setup|Connection created/);assert.equal(document.querySelector('input[type=password]'),null);
});
test('commerce current connection creation still displays one-time setup',async(t)=>{
 const root=createRoot(document.getElementById('root'));t.after(async()=>act(async()=>root.unmount()));
 const api=async(path,options={})=>{if(options.method==='POST')return {id:'new',name:'Synthetic new store',channel:'test',setup_secret:'SYNTHETIC-CURRENT-SECRET'};if(path.endsWith('/bank-accounts')||path.endsWith('/connections'))return [];return {connection:{id:'new',status:'paused',config:{}},orders:[],stock:[],links:[],outbox:[],reconciliations:[],summary:{}};};
 await act(async()=>root.render(React.createElement(components.CommerceWorkspace,{company:{id:'c',name:'Synthetic',role:'owner'},records:[],api})));await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Connect Bagisto').click());await act(async()=>submit(document.querySelector('form')));assert.equal(document.querySelector('input[type=password]').value,'SYNTHETIC-CURRENT-SECRET');assert.match(document.body.textContent,/Synthetic new store/);
});
for(const action of ['Create invoice','Cancel unfulfilled order'])for(const outcome of ['success','unknown','definitive','readfailure'])test(`commerce order ${action} ${outcome} preserves newer dialog and original retry payload`,async(t)=>{
 const root=createRoot(document.getElementById('root'));t.after(async()=>act(async()=>root.unmount()));let finish,fail;const commands=[];
 const orders=['A','B'].map(id=>({id,external_id:id,number:'ORDER-'+id,amount:'100',status:'open',snapshot:{items:[{id:'line-'+id,name:'Goods '+id,quantity:5,invoiced:0,shipped:0}]}}));
 const api=async(path,options={})=>{if(options.method==='POST'){commands.push(JSON.parse(options.body));if(commands.length===1)return new Promise((resolve,reject)=>{finish=resolve;fail=reject;});return {status:'pending'};}if(path.endsWith('/bank-accounts'))return [];if(path.endsWith('/connections'))return [{id:'store',name:'Store',channel:'test'}];if(outcome==='readfailure'&&commands.length)throw Error('Synthetic follow-up read failed');return {connection:{id:'store',status:'active',config:{}},orders,stock:[],links:[],outbox:[],reconciliations:[],summary:{}};};
 await act(async()=>root.render(React.createElement(components.CommerceWorkspace,{company:{id:'c',name:'Synthetic',role:'editor'},records:[],api})));await act(async()=>[...document.querySelectorAll('.commerce-tabs button')].find(b=>b.textContent==='orders').click());
 await act(async()=>[...document.querySelectorAll('button')].filter(b=>b.textContent==='Open order')[0].click());await change(document.querySelector('[aria-label="Action quantity for Goods A"]'),'1');await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent===action).click());
 await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Close').click());await act(async()=>[...document.querySelectorAll('button')].filter(b=>b.textContent==='Open order')[1].click());await change(document.querySelector('[aria-label="Action quantity for Goods B"]'),'3');
 await act(async()=>['success','readfailure'].includes(outcome)?finish({status:'pending'}):fail(Object.assign(Error('Unknown order response'),{status:outcome==='unknown'?0:422})));
 assert.match(document.querySelector('[role=dialog]').textContent,/ORDER-B/);
 if(outcome==='readfailure'){assert.match(document.body.textContent,/Do not queue it again/);assert.doesNotMatch(document.body.textContent,/Retry original order command/);assert.equal(commands.length,1);}
 if(outcome==='definitive'){assert.equal([...document.querySelectorAll('button')].find(b=>b.textContent==='Create invoice').disabled,false);assert.doesNotMatch(document.body.textContent,/Retry original order command/);}
 if(outcome==='unknown'){assert.equal([...document.querySelectorAll('button')].find(b=>b.textContent==='Create invoice').disabled,true);await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Retry original order command').click());assert.equal(commands.length,2);assert.deepEqual(commands[1],commands[0]);assert.match(document.querySelector('[role=dialog]').textContent,/ORDER-B/);}
});
