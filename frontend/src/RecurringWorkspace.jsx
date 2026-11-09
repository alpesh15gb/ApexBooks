import { businessDate } from "./businessDate.js";
import React, { useEffect, useState, useRef } from 'react';
import { CalendarDays, Plus, RefreshCw, ArrowRight } from 'lucide-react';
import { usePostingRequest, pendingPostingMessage } from './usePostingRequest.js';
const today = () => businessDate();
const draftKinds = ['estimate', 'proforma', 'sales_order', 'purchase_order'];
const label = kind => ({estimate:'Estimate',proforma:'Pro forma',sales_order:'Sales order',purchase_order:'Purchase order'})[kind] || kind;

export default function RecurringWorkspace({ companyId, role, records, api, Modal, onReview, onRefresh }) {
  const [templates, setTemplates] = useState(null), [due, setDue] = useState([]), [error, setError] = useState(''), [revision, setRevision] = useState(0), [action, setAction] = useState(null), [search, setSearch] = useState(''), [businessDate, setBusinessDate] = useState(today);
  const live = useRef(true);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  const canWrite = ['owner','editor'].includes(role);
  useEffect(() => {
    let active = true; setTemplates(null); setError('');
    Promise.all([api(`/companies/${companyId}/recurring-templates`),api(`/companies/${companyId}/recurring-templates/due`)])
      .then(([library, worklist]) => { if (active) { setTemplates(library.templates); setDue(worklist.rows); setBusinessDate(worklist.business_date || worklist.as_of || today()); } })
      .catch(reason => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [companyId, revision]);
  const sources = records.filter(row => draftKinds.includes(row.kind) && !row.converted_to && !row.data?.vyapar_converted);
  const visible = (templates || []).filter(row => `${row.name} ${row.party_name || ''}`.toLowerCase().includes(search.toLowerCase()));
  const complete = async result => {
    setAction(null); setRevision(value => value + 1);
    if (result?.record) { await onRefresh(); if (live.current) onReview(result.record); }
  };
  return <div className="recurring-workspace"><header className="page-heading"><div><div className="eyebrow green">PLANNED, NEVER AUTO-POSTED</div><h1>Recurring drafts</h1><p>Prepare repeat quotations, orders and purchase orders on a schedule. Every occurrence needs your review; nothing automatically invoices, moves stock or charges money.</p></div><div className="heading-actions"><button className="button secondary" onClick={() => setRevision(value => value + 1)}><RefreshCw size={16}/>Refresh</button>{canWrite && <button className="button primary" disabled={!templates} onClick={() => setAction({ mode:'create' })}><Plus size={16}/>New template</button>}</div></header>
    {error && <p className="error banner" role="alert">{error}</p>}
    {!templates && !error && <p role="status">Loading recurring draft schedules…</p>}
    {templates && <><section className="panel recurring-due"><div className="panel-header"><div><h2><CalendarDays size={20}/> Due for review</h2><p>Earliest ungenerated occurrence per active template · through {businessDate} · India business date (IST)</p></div><strong>{due.length} due</strong></div>{due.length ? due.map(row => <article className="recurring-row" key={row.id}><div><strong>{row.name}</strong><small>{row.party_name || 'Party not selected'} · {label(row.draft_kind)}</small></div><div><strong>{row.next_due}</strong><small>{Number(row.overdue_days)>0 ? `${row.overdue_days} days overdue` : 'Due today'}</small></div>{canWrite ? <button className="button primary" onClick={() => setAction({ mode:'generate', template:row })}>Create draft & review<ArrowRight size={15}/></button> : <span>Read-only</span>}</article>) : <div className="empty"><CalendarDays size={24}/><strong>No drafts due today</strong><p>Active schedules will appear here when their next date arrives. Paused schedules never generate drafts.</p></div>}</section>
    <section className="panel recurring-library"><div className="panel-header"><div><h2>Template library</h2><p>{templates.length} of 100 templates · generated drafts remain in their normal registers</p></div><label className="search"><input aria-label="Search recurring templates" value={search} onChange={event => setSearch(event.target.value)} placeholder="Find template or party"/></label></div>{visible.length ? visible.map(row => <article className="recurring-row" key={row.id}><div><strong>{row.name}</strong><small>{label(row.draft_kind)} · {row.party_name || 'No party'}</small><small>Every {row.interval} {row.frequency === 'monthly' ? 'month(s)' : 'week(s)'} · starts {row.start_date}{row.end_date ? ` · ends ${row.end_date}` : ''}</small></div><div><span className="status-pill">{row.is_active ? 'Active' : 'Paused'}</span><small>Next: {row.next_due || 'Schedule complete'}</small><small>{row.generated_count || 0} generated{row.last_generated_date ? ` · last ${row.last_generated_date}` : ''}</small></div><button className="button secondary" onClick={() => setAction({ mode:canWrite ? 'edit' : 'inspect', template:row })}>{canWrite ? 'Review / edit' : 'Inspect template'}</button></article>) : <div className="empty"><strong>{templates.length ? 'No matching templates' : 'Start from a reviewed draft'}</strong><p>Create an estimate, pro forma, sales order or purchase order first, then save its inputs as a repeatable template. Expenses and posted invoices are not automatically repeated.</p></div>}</section></>}
    {action && <RecurringAction key={`${action.mode}-${action.template?.id || 'new'}`} action={action} businessDate={businessDate} companyId={companyId} sources={sources} api={api} Modal={Modal} close={() => setAction(null)} complete={complete}/>}</div>;
}

function RecurringAction({ action, businessDate, companyId, sources, api, Modal, close, complete }) {
  const row = action.template, creating = action.mode === 'create', generating = action.mode === 'generate', inspecting = action.mode === 'inspect';
  const [form,setForm] = useState({name:row?.name || '',source_record_id:'',start_date:businessDate,frequency:'monthly',interval:'1',end_date:'',is_active:row?.is_active !== false}), [error,setError] = useState(''), [dirty,setDirty] = useState(false), [detail,setDetail] = useState(null);
  const [key] = useState(() => crypto.randomUUID()); const posting = usePostingRequest({ definitiveRetryStatuses: [409] }); const { busy,pending } = posting;
  const requestClose = () => { if (busy || pending) return; if (!dirty || window.confirm('Discard unsaved template changes? No new draft has been created.')) close(); };
  useEffect(() => {
    const guard = event => { if (dirty || pending || busy) { event.preventDefault(); event.returnValue=''; } };
    window.addEventListener('beforeunload',guard); window.addEventListener('apex-close-workflow',requestClose);
    return () => { window.removeEventListener('beforeunload',guard);window.removeEventListener('apex-close-workflow',requestClose); };
  });
  useEffect(() => {
    if (!row || generating) return;
    let active=true;
    api(`/companies/${companyId}/recurring-templates/${row.id}`).then(result=>{if(active)setDetail(result);}).catch(reason=>{if(active)setError(reason.message);});
    return()=>{active=false;};
  },[companyId,row?.id,generating]);
  const change = event => { setDirty(true);setForm(current=>({...current,[event.target.name]:event.target.type==='checkbox'?event.target.checked:event.target.value})); };
  async function submit(event) {
    event.preventDefault(); if (busy || inspecting) return; setError('');
    const path = generating ? `/recurring-templates/${row.id}/occurrences` : creating ? '/recurring-templates' : `/recurring-templates/${row.id}`;
    const body = generating ? {occurrence_date:row.next_due} : creating ? {...form,interval:Number(form.interval),end_date:form.end_date || null} : {version:row.version,name:form.name,is_active:form.is_active,...(form.source_record_id ? {source_record_id:form.source_record_id} : {})};
    try {
      const outcome = await posting.run(() => api(`/companies/${companyId}${path}`, {method:creating||generating?'POST':'PUT',headers:{'Idempotency-Key':key},body:JSON.stringify(body)}));
      if (outcome) { setDirty(false); await complete(outcome.value); }
    } catch(reason) { setError(reason.message); }
  }
  return <Modal title={generating ? 'Create one scheduled draft' : creating ? 'New recurring draft template' : inspecting ? 'Template details' : 'Edit recurring template'} subtitle="No automatic posting, stock movement or payment" close={requestClose}><form className="form-grid" onSubmit={submit}><fieldset className="form-grid full submission-fields" disabled={busy||pending||inspecting}>
    {generating ? <div className="info-box full"><strong>{row.name} · {row.next_due}</strong><p>This creates one saved {label(row.draft_kind).toLowerCase()} and opens its editor. Closing the editor afterward keeps that draft in its register. Creating the same occurrence again returns the same draft, not a duplicate.</p></div> : <><label className="full">Template name<input required maxLength={120} name="name" value={form.name} onChange={change}/></label>{!inspecting && <label className="full">{creating ? 'Reviewed source draft' : 'Refresh future inputs from a different reviewed draft (optional)'}<select required={creating} name="source_record_id" value={form.source_record_id} onChange={change}><option value="">{creating ? 'Select a saved draft' : 'Keep saved template inputs'}</option>{sources.map(source=><option key={source.id} value={source.id}>{source.number || label(source.kind)} · {source.name}</option>)}</select><small>Prices, items and addresses are copied explicitly. Previously generated drafts never change.</small></label>}
    {creating ? <><label>First occurrence<input required type="date" name="start_date" value={form.start_date} onChange={change}/></label><label>Repeat<select name="frequency" value={form.frequency} onChange={change}><option value="monthly">Monthly</option><option value="weekly">Weekly</option></select></label><label>Every<input required type="number" min="1" max="12" step="1" name="interval" value={form.interval} onChange={change}/></label><label>End date (optional)<input type="date" min={form.start_date} name="end_date" value={form.end_date} onChange={change}/></label><p className="detail-caption full">Monthly schedules keep the original day, using the month's last day when needed. Dates are fixed after creating a template; pause and create a replacement to change cadence.</p></> : <p className="info-box full">Every {row.interval} {row.frequency === 'monthly' ? 'month(s)' : 'week(s)'} from {row.start_date}. Schedule dates are fixed; pause this template and create a replacement to change them.</p>}
    <label className="full"><span><input type="checkbox" name="is_active" checked={form.is_active} onChange={change}/> Active schedule</span><small>Pausing stops new occurrences, not existing drafts or posted transactions.</small></label></>}
    </fieldset>{detail?.draft && <section className="full"><h3>Saved template inputs</h3><p>{label(detail.draft.kind)} · {detail.draft.name}</p><div className="table-wrap" tabIndex={0}><table><thead><tr><th>Item</th><th>Qty</th><th>Rate</th><th>Discount</th><th>Tax</th></tr></thead><tbody>{(detail.draft.data?.lines || []).map((line,index)=><tr key={index}><td>{line.description}</td><td>{line.quantity}</td><td>{line.rate} {line.price_includes_tax ? '(incl. tax)' : '(excl. tax)'}</td><td>{line.discount_amount != null ? `₹${line.discount_amount} fixed` : `${line.discount_percent || '0'}%`}</td><td>{line.gst_rate || '0'}% · {line.tax_treatment || 'taxable'}</td></tr>)}</tbody></table></div><p>Document discount: {detail.draft.data?.document_discount_percent || '0'}%{detail.draft.data?.round_total ? ' · round final total' : ''}</p>{detail.draft.data?.shipping_address && <p>Delivery: {detail.draft.data.shipping_address}</p>}<small>Generated dates and totals are recalculated by the API. Existing source documents and past occurrences remain unchanged.</small></section>}
    {pending&&!busy&&<p className="info-box full" role="status">{pendingPostingMessage}</p>}{error&&<p className="error full" role="alert">{error}</p>}<div className="modal-actions full"><button type="button" className="button secondary" disabled={busy||pending} onClick={requestClose}>{inspecting?'Close':'Cancel'}</button>{!inspecting&&<button className="button primary" disabled={busy||(creating&&!sources.length)}>{busy?'Saving…':generating?'Create draft & review':creating?'Save template':'Save changes'}</button>}</div></form></Modal>;
}
