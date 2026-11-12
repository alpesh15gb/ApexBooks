import {createCommerceRecovery} from './commerceRecovery.js';
import { businessDate } from "./businessDate.js";
import React, {useEffect,useRef,useState,useSyncExternalStore} from 'react';
const today = businessDate;
const Field=({label,children})=><label className="commerce-field"><span>{label}</span>{children}</label>;
export default function CommerceMoneyForm({workspace,banks,busy,send,onDone,recovery}){
  const [f,setF]=useState({kind:'capture',order:'',source:'',date:today(),amount:'',target:'',net:'',fee:'0',bank:'',supply:'goods',gst:'0'});
  const localRecovery=useRef(null);if(!localRecovery.current)localRecovery.current=createCommerceRecovery();const pending=recovery||localRecovery.current;
  const recoveryState=useSyncExternalStore(pending.subscribe,pending.snapshot,pending.snapshot);const {busy:submitting,uncertain,error,completed}=recoveryState;
  const mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  const [captures,setCaptures]=useState([]),[refunds,setRefunds]=useState([]),[quantities,setQuantities]=useState({});
  const change=(key,value)=>{if(['kind','order','target'].includes(key))setQuantities({});setF(old=>({...old,[key]:value,...(['kind','order'].includes(key)?{target:''}:{})}));};
  const links=workspace.links, docs=type=>links.filter(r=>r.entity_type===type&&r.snapshot.order_id===f.order);
  const credits=docs('credit'), note=credits.find(r=>r.external_id===f.target);
  const unsettled=type=>links.filter(r=>r.entity_type===type&&!r.snapshot._settled);
  const toggle=(list,set,id)=>set(list.includes(id)?list.filter(x=>x!==id):[...list,id]);
  const input=(label,key,type='text',required=true)=><Field label={label}><input required={required} type={type} step={type==='number'?'0.01':undefined} min={type==='number'?'0':undefined} value={f[key]} onChange={e=>change(key,e.target.value)}/></Field>;
  const select=(label,key,options,required=true)=><Field label={label}><select required={required} value={f[key]} onChange={e=>change(key,e.target.value)}>{options.map(([id,text])=><option key={id} value={id}>{text}</option>)}</select></Field>;
  async function submit(e){e.preventDefault();if(pending.snapshot().busy||busy||workspace.connection.status!=='active')return;pending.update({busy:true,error:'',completed:false});try{
    if(!pending.snapshot().request){
    let operation,data={order_id:f.order,date:f.date,amount:f.amount};
    if(f.kind==='capture'){operation='payment.capture';if(f.target)data.allocations=[{invoice_id:f.target,amount:f.amount}];else Object.assign(data,{advance_supply:f.supply,advance_gst_rate:f.gst,place_of_supply:workspace.connection.config.capabilities?.company_state_code||''});}
    else if(f.kind==='refund'){operation='payment.refund';const [type,...id]=f.target.split(':');data[type==='credit'?'credit_id':'capture_id']=id.join(':');}
    else if(f.kind==='receipt'){operation='return.receive';data={order_id:f.order,date:f.date,credit_id:f.target,lines:Object.entries(quantities).filter(([id,q])=>note?.snapshot.lines?.some(line=>line.product_id===id)&&Number(q)>0).map(([product_id,quantity])=>({product_id,quantity}))};if(!data.lines.length)throw new Error('Enter the quantities physically received.');}
    else{operation='settlement.record';const gross=captures.reduce((sum,id)=>sum+Number(links.find(r=>r.entity_type==='capture'&&r.external_id===id)?.snapshot.amount||0),0);data={date:f.date,gross:gross.toFixed(2),net:f.net,fee:f.fee||'0',capture_ids:captures,refund_ids:refunds,bank_account_id:f.bank};}
    pending.update({request:{operation,payload:JSON.parse(JSON.stringify({source_id:f.source.trim(),confirmed:true,data}))}});
    }
    const original=pending.snapshot().request;await send(original.operation,original.payload);pending.update({request:null,uncertain:false,error:'',completed:true});if(!mounted.current)return;setF(old=>({...old,source:'',amount:''}));setCaptures([]);setRefunds([]);setQuantities({});onDone();
  }catch(e){const original=pending.snapshot().request;const unresolved=original&&(e.status==null||e.status===0||e.status===408||e.status===409||e.status>=500);pending.update({request:unresolved?original:null,uncertain:Boolean(unresolved),error:e.message});}finally{pending.update({busy:false});}}

  return <form className="commerce-card" onSubmit={submit}><h3>Payments, payouts & physical returns</h3><p>Record confirmed source transactions. Invoice status alone does not prove money was received.</p>{error&&<div className="commerce-alert error" role="alert">{error}</div>}{completed&&<p role="status">The original source command was accepted. Review delivery results before recording it again.</p>}<fieldset className="commerce-money-fields" disabled={uncertain||busy||submitting||workspace.connection.status!=='active'}><div className="commerce-fields">
    {select('Action','kind',[['capture','Payment received / captured'],['refund','Cash / gateway refund'],['settlement','Gateway settlement'],['receipt','Goods physically received']])}
    {input('Bank / provider / receipt reference','source')}{input('Accounting date','date','date')}
    {f.kind!=='settlement'&&select('Store order','order',[['','Choose…'],...workspace.orders.map(r=>[r.external_id,r.number])])}
    {f.kind==='capture'&&select('Invoice allocation','target',[['','Unapplied customer advance'],...docs('invoice').map(r=>[r.external_id,`Invoice ${r.external_id} · ₹${r.snapshot.amount}`])],false)}
    {f.kind==='refund'&&select('Original credit or advance','target',[['','Choose…'],...credits.map(r=>[`credit:${r.external_id}`,`Credit ${r.external_id} · ₹${r.snapshot.amount}`]),...docs('capture').map(r=>[`capture:${r.external_id}`,`Advance ${r.external_id} · ₹${r.snapshot.amount}`])])}
    {f.kind==='receipt'&&select('Financial credit note','target',[['','Choose…'],...credits.map(r=>[r.external_id,`Credit ${r.external_id}`])])}
    {['capture','refund'].includes(f.kind)&&input('Amount (₹)','amount','number')}
    {f.kind==='capture'&&!f.target&&<>{select('Advance supply','supply',[['goods','Goods'],['services','Services']])}{f.supply==='services'&&select('Advance GST rate','gst',['0','5','12','18','28'].map(r=>[r,`${r}%`]))}</>}
  </div>
  {f.kind==='receipt'&&<div className="commerce-fields">{(note?.snapshot.lines||[]).map(line=><Field key={line.product_id} label={`${workspace.stock.find(r=>r.external_id===line.product_id)?.name||line.product_id} · credited ${line.quantity}`}><input type="number" min="0" max={line.quantity} step="0.001" value={quantities[line.product_id]||''} onChange={e=>setQuantities({...quantities,[line.product_id]:e.target.value})}/></Field>)}</div>}
  {f.kind==='settlement'&&<><div className="commerce-grid">{[['capture',captures,setCaptures,'Captured receipts in this payout'],['refund',refunds,setRefunds,'Refunds deducted by provider']].map(([type,list,set,label])=><section key={type}><h3>{label}</h3>{unsettled(type).map(r=><label className="commerce-check" key={r.id}><input type="checkbox" checked={list.includes(r.external_id)} onChange={()=>toggle(list,set,r.external_id)}/>{r.external_id} · ₹{r.snapshot.amount}</label>)}</section>)}</div><div className="commerce-fields">{input('Bank net received (₹)','net','number')}{input('Provider fee, excluding supplier GST (₹)','fee','number',false)}{select('Destination bank account','bank',[['','Choose…'],...banks.filter(b=>b.id!==workspace.connection.config.gateway_bank_id).map(b=>[b.id,b.name])])}</div><p className="commerce-muted">Captured gross − selected refunds − fee must equal bank net. Record GST on provider fees using its supplier bill.</p></>}
  <button className="primary" disabled={busy||submitting||workspace.connection.status!=='active'}>{submitting?'Queueing source…':'Confirm source & queue'}</button></fieldset>{uncertain&&<div className="commerce-alert" role="status"><p>The previous response is uncertain. Retry the original source command before recording it again. Reference: {recoveryState.request?.payload.source_id || "not supplied"}.</p><p>Keep this workspace open until the result is recovered. Reloading or signing out clears this local recovery state.</p><button type="submit" className="primary" disabled={busy||submitting||workspace.connection.status!=='active'}>{submitting?'Recovering original command…':'Retry original source command'}</button></div>}</form>;
}
