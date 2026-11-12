import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ShoppingBag, RefreshCw, Plus, Link2, ShieldCheck, ArrowUpRight, AlertCircle, Package, CheckCircle2 } from 'lucide-react';
import './commerce.css';
import CommerceMoneyForm from './CommerceMoneyForm.jsx';

const money = value => new Intl.NumberFormat('en-IN', {style:'currency', currency:'INR'}).format(Number(value || 0));
const human = value => String(value || '').replaceAll('_', ' ').replaceAll('.', ' · ');
const commandId = () => crypto.randomUUID();
const Field = ({label, children}) => <label className="commerce-field"><span>{label}</span>{children}</label>;
const Empty = ({children}) => <div className="commerce-empty"><ShoppingBag size={28}/><p>{children}</p></div>;

export default function CommerceWorkspace({company, records, api, onPdf}) {
  const [connections, setConnections] = useState([]), [selected, setSelected] = useState(''), [workspace, setWorkspace] = useState(null);
  const [banks, setBanks] = useState([]), [tab, setTab] = useState('overview'), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [adding, setAdding] = useState(false), [setup, setSetup] = useState(null), [notice, setNotice] = useState('');
  const [form, setForm] = useState({name:'', base_url:'', channel:'default', gateway_bank_id:'default'});
  const [mapping, setMapping] = useState({entity_type:'product', external_id:'', record_id:'', sku:''});
  const [scan, setScan] = useState([]), [order, setOrder] = useState(null), [quantities, setQuantities] = useState({});
  const [carrier, setCarrier] = useState(''), [tracking, setTracking] = useState('');
  const alive = useRef(true), requestVersion = useRef(0);
  const root = `/companies/${company.id}/commerce/connections`;
  const owner = company.role === 'owner', canWrite = ['owner','editor'].includes(company.role);
  const connection = workspace?.connection, path = `${root}/${selected}`;
  useEffect(() => {alive.current = true; return () => {alive.current = false; requestVersion.current++;};}, []);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([api(root, {signal:controller.signal}), api(`/companies/${company.id}/bank-accounts`, {signal:controller.signal})])
      .then(([rows, accounts]) => {setConnections(rows); setBanks(accounts); setSelected(rows[0]?.id || '');})
      .catch(e => {if(e.name !== 'AbortError') setError(e.message);});
    return () => controller.abort();
  }, [api, root, company.id]);
  const refresh = useCallback(async () => {
    if (!selected) return;
    const version = ++requestVersion.current;
    const data = await api(`${root}/${selected}/workspace`);
    if (alive.current && version === requestVersion.current) {
      setWorkspace(data);
      const result = data.outbox.find(row => row.operation === 'catalogue.scan' && row.status === 'done');
      if (result) setScan(result.result.products || []);
    }
  }, [selected, api, root]);
  useEffect(() => {
    setWorkspace(null); setOrder(null); setScan([]); setSetup(null); setError('');
    refresh().catch(e => {if(alive.current) setError(e.message);});
    const timer = setInterval(() => refresh().catch(() => {}), 5000);
    return () => {clearInterval(timer); requestVersion.current++;};
  }, [refresh]);
  async function act(action, success='Saved') {
    setBusy(true); setError(''); setNotice('');
    try {await action(); if(alive.current) {setNotice(success); await refresh();}}
    catch(e) {if(alive.current) setError(e.message);}
    finally {if(alive.current) setBusy(false);}
  }
  const moneyContext = `${company.id}:${selected}`;
  const currentMoneyContext = useRef(moneyContext);
  currentMoneyContext.current = moneyContext;
  const pendingCommands = useRef(new Map());
  const send = async (operation, payload={}) => {
    const intent = JSON.stringify([path,operation,payload]);
    const id = pendingCommands.current.get(intent) || commandId();
    pendingCommands.current.set(intent,id);
    const result = await api(`${path}/commands`, {method:'POST', body:JSON.stringify({command_id:id, operation, payload})});
    pendingCommands.current.delete(intent);
    return result;
  };
  async function createConnection(event) {
    event.preventDefault();
    await act(async () => {
      const result = await api(root, {method:'POST', body:JSON.stringify(form)});
      const {setup_secret: oneTimeSecret, ...safe} = result;
      setConnections(old => [...old, safe]); setSelected(result.id); setAdding(false);
      // Keep the one-time credential in memory only. Selection effect runs
      // first; this dedicated state is set after React's connection refresh.
      pendingSetup.current = result;
    }, 'Connection created. Install the server bridge, then verify it.');
  }
  const pendingSetup = useRef(null);
  useEffect(() => {if(pendingSetup.current?.id === selected) {setSetup(pendingSetup.current); pendingSetup.current = null;}}, [selected]);
  function openOrder(row) {
    setOrder(row); setQuantities(Object.fromEntries((row.snapshot.items || []).map(line => [line.id, '']))); setCarrier(''); setTracking('');
  }
  const pending = (workspace?.summary?.inbox?.pending || 0) + (workspace?.summary?.outbox?.pending || 0);
  const review = (workspace?.summary?.inbox?.review || 0) + (workspace?.summary?.outbox?.review || 0);
  const active = connection?.status === 'active';
  const rows = mapping.entity_type === 'product' ? records.filter(r => r.kind === 'item') : records.filter(r => r.kind === 'party');
  return <div className="commerce-workspace">
    <div className="commerce-heading"><div><div className="commerce-eyebrow">SALES CHANNELS · {company.name}</div><h2><ShoppingBag size={25}/> Ecommerce</h2><p>Orders, inventory and books connected to the right company.</p></div>
      <div className="commerce-actions"><button disabled={busy || !selected} onClick={() => act(refresh, 'Updated')}><RefreshCw size={16}/>Refresh</button>{owner && <button className="primary" onClick={() => setAdding(!adding)}><Plus size={16}/>Connect Bagisto</button>}</div></div>
    {error && <div role="alert" className="commerce-alert error"><AlertCircle size={18}/>{error}</div>}
    {notice && <div role="status" className="commerce-alert"><CheckCircle2 size={18}/>{notice}</div>}
    {adding && <form onSubmit={createConnection} className="commerce-card"><h3>Connect a Bagisto channel</h3><p>Each connection belongs to {company.name}. Use a separate channel and inventory source for another company.</p><div className="commerce-fields">
      <Field label="Store name"><input required maxLength={100} value={form.name} onChange={e => setForm({...form,name:e.target.value})}/></Field>
      <Field label="Store HTTPS origin"><input required type="url" placeholder="https://shop.example.com" value={form.base_url} onChange={e => setForm({...form,base_url:e.target.value})}/></Field>
      <Field label="Bagisto channel code"><input required value={form.channel} onChange={e => setForm({...form,channel:e.target.value})}/></Field>
      <Field label="Gateway clearing account"><select value={form.gateway_bank_id} onChange={e => setForm({...form,gateway_bank_id:e.target.value})}><option value="default">Default bank clearing</option>{banks.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></Field>
    </div><button className="primary" disabled={busy}>Create connection</button><button type="button" onClick={() => setAdding(false)}>Cancel</button></form>}
    {setup && <section className="commerce-card commerce-setup"><h3><ShieldCheck size={19}/> Server bridge setup</h3><p>This credential is shown once. Save it in the Bagisto server configuration.</p><Field label="Connection ID"><input readOnly value={setup.id}/></Field><Field label="One-time connection secret"><input readOnly type="password" autoComplete="off" value={setup.setup_secret}/></Field><button onClick={() => navigator.clipboard.writeText(JSON.stringify({connection_id:setup.id,secret:setup.setup_secret,channel:setup.channel})).then(() => setNotice('Setup copied. Store it on your Bagisto server.')).catch(() => setError('Clipboard unavailable; select and copy the setup values.'))}>Copy server setup</button><button onClick={() => setSetup(null)}>I have saved this</button></section>}
    {!connections.length && !adding ? <div className="commerce-card"><Empty>Connect a Bagisto store to bring its orders, payments and stock into this company.</Empty></div> : <>
      <div className="commerce-store-bar"><Field label="Store channel"><select disabled={busy} value={selected} onChange={e => setSelected(e.target.value)}>{connections.map(c => <option key={c.id} value={c.id}>{c.name} · {c.channel}</option>)}</select></Field>
        {connection && <><span className={`commerce-status ${connection.status}`}>{human(connection.status)}</span><span className="commerce-muted">INR · {connection.base_url}</span></>}
        {owner && connection && <div className="commerce-actions"><button disabled={busy} onClick={() => act(() => api(`${path}/verify`,{method:'POST'}), 'Bridge verified')}>Verify bridge</button><button disabled={busy || (!active && !connection.config?.verified)} onClick={() => act(() => api(`${path}/state`,{method:'PUT',body:JSON.stringify({status:active?'paused':'active'})}), active?'Connection paused':'Connection active')}>{active?'Pause':'Activate'}</button></div>}
      </div>
      {workspace && <><div className="commerce-metrics">{[[ShoppingBag,'Store orders',workspace.orders.length],[Package,'Mapped SKUs',workspace.stock.length],[RefreshCw,'Waiting delivery',pending],[AlertCircle,'Needs review',review]].map(([Icon,label,value]) => <div className="commerce-metric" key={label}><Icon size={20}/><span>{label}</span><strong>{value}</strong></div>)}</div>
        <nav className="commerce-tabs" aria-label="Ecommerce sections">{['overview','catalogue','orders','payments','deliveries','reconciliation'].map(key => <button key={key} className={tab===key?'selected':''} onClick={() => setTab(key)}>{human(key)}</button>)}</nav>
        {tab==='payments'&&canWrite&&<CommerceMoneyForm key={`${company.id}:${selected}`} workspace={workspace} banks={banks} busy={busy} send={async(operation,payload)=>{await send(operation,payload);if(alive.current&&currentMoneyContext.current===moneyContext)await refresh();}} onDone={()=>setNotice('Source transaction queued. Review delivery results before recording it again.')}/>}
        {tab === 'overview' && <div className="commerce-grid"><section className="commerce-card"><h3>Connection checklist</h3>{[[true,'Company ownership and channel saved'],[connection.config?.verified,'Server bridge verified'],[active,'Connection active'],[workspace.stock.length>0,'Store SKUs mapped'],[workspace.reconciliations.some(r=>r.status==='balanced'),'Reconciliation completed']].map(([done,label]) => <div className="commerce-check" key={label}><CheckCircle2 size={18} className={done?'complete':''}/>{label}</div>)}<p className="commerce-muted">Checkout reserves stock before accepting an order. Invoices post sales and GST; shipments update fulfilment. Captures enter clearing, and settlements move the bank net and fees.</p></section><section className="commerce-card"><h3>Review and repair</h3><p>Unmapped items, tax differences and unsupported source rules stay visible for review. Correct the mapping or source, then retry the delivery.</p><div className="commerce-actions"><button onClick={() => setTab('deliveries')}>Open delivery queue <ArrowUpRight size={16}/></button>{canWrite && <button disabled={!active||busy} onClick={() => act(() => send('history.scan',{after_id:0}), 'History repair queued. Existing source IDs will be reused.')}>Scan store history</button>}</div></section></div>}
        {tab === 'catalogue' && <><section className="commerce-card"><div className="commerce-heading"><div><h3>Product and customer mappings</h3><p>Choose the accounting item or party in this company explicitly.</p></div>{canWrite && <button disabled={!active||busy} onClick={() => act(() => send('catalogue.scan'), 'Store catalogue scan queued')}>Read store catalogue</button>}</div>
          {canWrite && <form onSubmit={e => {e.preventDefault();act(() => api(`${path}/links`,{method:'POST',body:JSON.stringify(mapping)}),'Mapping saved');}}><div className="commerce-fields"><Field label="Mapping type"><select value={mapping.entity_type} onChange={e => setMapping({entity_type:e.target.value,external_id:'',record_id:'',sku:''})}><option value="product">Product → Item</option><option value="customer">Customer → Party</option></select></Field><Field label="Store identity"><input required list="commerce-store-products" value={mapping.external_id} onChange={e => {const product=scan.find(p=>p.external_id===e.target.value);setMapping({...mapping,external_id:e.target.value,...(product?{sku:product.sku}:{})});}}/><datalist id="commerce-store-products">{scan.map(p=><option key={p.external_id} value={p.external_id}>{p.sku} · {p.name}</option>)}</datalist></Field><Field label={mapping.entity_type==='product'?'Accounting item':'Accounting party'}><select required value={mapping.record_id} onChange={e=>setMapping({...mapping,record_id:e.target.value})}><option value="">Choose…</option>{rows.map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</select></Field>{mapping.entity_type==='product'&&<Field label="Exact store SKU"><input required value={mapping.sku} onChange={e=>setMapping({...mapping,sku:e.target.value})}/></Field>}</div><button className="primary" disabled={busy}><Link2 size={16}/>Save mapping</button></form>}</section>
          <section className="commerce-card"><div className="commerce-heading"><h3>Sellable inventory</h3>{canWrite&&<button disabled={!active||busy} onClick={()=>act(()=>send('catalogue.publish'),'Prices and stock publication queued')}>Publish accounting prices & stock</button>}</div><div className="commerce-table"><table><thead><tr><th>Item / SKU</th><th>Book stock</th><th>Reserved</th><th>Sellable</th><th>Sale rate</th></tr></thead><tbody>{workspace.stock.map(r=><tr key={r.external_id}><td><strong>{r.name}</strong><small>{r.sku}</small></td><td>{r.book_quantity}</td><td>{r.reserved_quantity}</td><td>{r.available_quantity}</td><td>{money(r.sale_rate)}</td></tr>)}</tbody></table></div>{!workspace.stock.length&&<Empty>No products mapped yet.</Empty>}</section></>}
        {tab === 'orders' && <section className="commerce-card"><h3>Store orders</h3><div className="commerce-table"><table><thead><tr><th>Order</th><th>Customer</th><th>Status</th><th>Total</th><th/></tr></thead><tbody>{workspace.orders.map(r=><tr key={r.id}><td><strong>{r.number}</strong><small>{r.external_id}</small></td><td>{records.find(p=>p.id===r.party_id)?.name||r.snapshot.customer_id}</td><td><span className="commerce-status">{human(r.status)}</span></td><td>{money(r.amount)}</td><td><button onClick={()=>openOrder(r)}>Open order</button></td></tr>)}</tbody></table></div>{!workspace.orders.length&&<Empty>Accepted store orders appear here after delivery.</Empty>}</section>}
        {tab === 'deliveries' && ['inbox','outbox'].map(direction=><section className="commerce-card" key={direction}><h3>{direction==='inbox'?'Store → Books':'Books → Store'}</h3><div className="commerce-table"><table><thead><tr><th>Action / identity</th><th>Status</th><th>Details</th><th/></tr></thead><tbody>{workspace[direction].map(r=><tr key={r.id}><td>{human(r.event_type||r.operation)}<small>{r.entity_id||r.command_id}</small></td><td><span className={`commerce-status ${r.status}`}>{r.status}</span></td><td>{r.error||r.result?.invoice_number||''}</td><td>{canWrite&&['review','retry'].includes(r.status)&&<button disabled={busy} onClick={()=>act(()=>api(`${path}/retry/${direction}/${r.id}`,{method:'POST'}),'Delivery queued for retry')}>Retry</button>}{onPdf&&r.event_type==='invoice.created'&&r.result?.record_id&&<button onClick={()=>onPdf({id:r.result.record_id,kind:'sales_invoice',number:r.result.invoice_number})}>Invoice PDF</button>}</td></tr>)}</tbody></table></div>{!workspace[direction].length&&<Empty>No deliveries yet.</Empty>}</section>)}
        {tab === 'reconciliation' && <section className="commerce-card"><div className="commerce-heading"><div><h3>Store reconciliation</h3><p>Compare source totals and mapped sellable stock. Results stay in this company’s audit trail.</p></div>{canWrite&&<button className="primary" disabled={!active||busy} onClick={()=>act(()=>send('reconcile.snapshot'),'Reconciliation queued')}>Reconcile now</button>}</div>{workspace.reconciliations.length?workspace.reconciliations.map(r=><div className="commerce-reconciliation" key={r.id}><span className={`commerce-status ${r.status}`}>{r.status}</span><time>{new Date(r.created_at).toLocaleString()}</time><p>{(r.report.stock_differences||[]).length} stock differences · Store invoices {money(r.report.store?.invoice_total)} · Store credits {money(r.report.store?.credit_total)}</p>{(r.report.stock_differences||[]).map(d=><p key={d.product_id}>Product {d.product_id}: Books {d.expected}, store {d.actual??'missing'}</p>)}</div>):<Empty>Run the first reconciliation after mapping products and importing orders.</Empty>}</section>}
      </>}
    </>}
    {order && <div className="commerce-dialog-backdrop"><section className="commerce-dialog" role="dialog" aria-modal="true" aria-labelledby="commerce-order-title"><div className="commerce-heading"><div><div className="commerce-eyebrow">BAGISTO ORDER</div><h3 id="commerce-order-title">{order.number} · {money(order.amount)}</h3></div><button onClick={()=>setOrder(null)}>Close</button></div><p>{human(order.status)} · Source {order.external_id}</p><div className="commerce-table"><table><thead><tr><th>Item</th><th>Ordered / invoiced / shipped</th><th>Action qty</th></tr></thead><tbody>{(order.snapshot.items||[]).map(line=><tr key={line.id}><td>{line.name}<small>{line.sku}</small></td><td>{line.quantity} / {line.invoiced} / {line.shipped}</td><td><input aria-label={`Action quantity for ${line.name}`} type="number" min="0" step="1" max={line.quantity} value={quantities[line.id]||''} onChange={e=>setQuantities({...quantities,[line.id]:e.target.value})}/></td></tr>)}</tbody></table></div>{canWrite&&<><div className="commerce-fields"><Field label="Carrier"><input value={carrier} onChange={e=>setCarrier(e.target.value)}/></Field><Field label="Tracking number"><input value={tracking} onChange={e=>setTracking(e.target.value)}/></Field></div><div className="commerce-actions">{[['order.invoice','Create invoice'],['order.ship','Create shipment'],['order.refund','Create credit / refund']].map(([operation,label])=><button key={operation} disabled={!active||busy} onClick={()=>act(async()=>{const items=Object.fromEntries(Object.entries(quantities).filter(([,q])=>Number(q)>0).map(([k,q])=>[k,Number(q)]));if(!Object.keys(items).length)throw new Error('Enter the quantities for this action.');await send(operation,{order_id:order.external_id,items,carrier,tracking});setOrder(null);},'Order action queued')}>{label}</button>)}<button disabled={!active||busy} onClick={()=>act(async()=>{await send('order.cancel',{order_id:order.external_id});setOrder(null);},'Cancellation queued')}>Cancel unfulfilled order</button></div><p className="commerce-muted">A credit note and a cash refund are separate accounting events. Source quantities and payment evidence are validated before posting.</p></>}</section></div>}
  </div>;
}
