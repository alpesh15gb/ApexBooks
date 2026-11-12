import {sessionFetch as fetch} from './sessionScope.js';
import React, { useRef, useState } from 'react';
import DocumentAmounts from './DocumentAmounts.jsx';
import StockRecordSummary from './StockRecordSummary.jsx';
import DocumentAttachments from './DocumentAttachments.jsx';
import { hasPendingPostings } from './postingRegistry.js';
import { ArrowRight, BellRing, CheckCircle2, Clock3, Download, FileText, MessageCircle, Pencil, Printer, X } from 'lucide-react';
import { canRemind, documentMessage, partyPhone, reminderMessage, whatsappUrl } from './whatsappShare.js';
import { relatedRecordActions, settlementLabel } from './recordLifecycle.js';
const drafts = new Set(['estimate', 'proforma', 'sales_order', 'purchase_order']);
const receiptKinds = new Set(['sales_invoice', 'pos', 'payment_in', 'estimate', 'proforma', 'sales_order', 'credit_note']);
const shareable = new Set(['sales_invoice', 'pos', 'estimate', 'proforma', 'sales_order', 'credit_note', 'payment_in', 'purchase_order']);
const amount = value => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(value || 0));

export default function TransactionDetail({ record, records, company, labels, loading, error, onClose, onRetry, onEdit, onRelated, onConvert, onPdf, onOpen, onCancelDocument, onManageCredits, api, features = [] }) {
  const [attachmentLocked, setAttachmentLocked] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelBusy, setCancelBusy] = useState(false);
  const [cancelError, setCancelError] = useState('');
  const cancellation = useRef(false);
  const locked = attachmentLocked || cancelBusy;
  async function confirmCancel() {
    if (cancellation.current || cancelReason.trim().length < 3) return;
    cancellation.current = true;
    setCancelBusy(true); setCancelError('');
    try { await onCancelDocument(record, cancelReason.trim()); setCancelOpen(false); setCancelReason(''); }
    catch (reason) { setCancelError(reason.message || 'Could not cancel this document'); }
    finally { cancellation.current = false; setCancelBusy(false); }
  }
  async function openWhatsApp(reminder) {
    // Open the tab synchronously so popup blockers allow it, then fill in the message.
    const tab = window.open('about:blank', '_blank');
    let upi = '';
    try {
      const response = await fetch(`/api/companies/${company.id}/document-branding`, { headers: { Authorization: `Bearer ${localStorage.token}` } });
      if (response.ok) upi = (await response.json()).upi_id || '';
    } catch { /* the message still works without a UPI ID */ }
    const text = reminder ? reminderMessage(record, company?.name || '', upi) : documentMessage(record, company?.name || '', upi);
    const url = whatsappUrl(partyPhone(record, records), text);
    if (tab) tab.location.href = url; else window.location.href = url;
  }
  const guarded = callback => (...args) => { if (!locked && !cancellation.current && !hasPendingPostings()) callback?.(...args); };
  onClose = guarded(onClose); onEdit = guarded(onEdit); onRelated = guarded(onRelated); onConvert = guarded(onConvert); onOpen = guarded(onOpen); onManageCredits = onManageCredits ? guarded(onManageCredits) : undefined;
  const writable = ['owner', 'editor'].includes(company?.role);
  const draft = drafts.has(record.kind);
  const cancelled = !!record.cancelled;
  const status = cancelled ? 'Cancelled' : record.converted_to ? 'Converted' : draft ? 'Open draft' : record.posted ? 'Posted' : 'Unposted';
  const actions = relatedRecordActions(record, writable);
  const cancellable = ['sales_invoice','purchase_bill','pos','expense','credit_note','debit_note','payment_in','payment_out','bank_transfer'].includes(record.kind) && record.posted && !cancelled && !!onCancelDocument && features.includes('document_cancellation');
  const editable = !cancelled && (['sales_invoice','purchase_bill','pos','expense','credit_note','debit_note','payment_in','payment_out','bank_transfer'].includes(record.kind) || draft);
  const pdf = ['sales_invoice','purchase_bill','pos','expense','credit_note','debit_note','payment_in','payment_out','customer_refund','supplier_refund','advance_refund'].includes(record.kind) || draft;
  const lines = record.data?.lines || [];
  const links = [
    ['Created from', record.data?.source_document_id],
    ['Converted to', record.converted_to],
    ['Original document', record.data?.applied_to],
  ].filter(([, id]) => id && id !== 'source-converted');
  const allocations = record.allocations || record.data?.allocations || [];
  const paidAgainst = records.filter(row => row.id !== record.id && !row.cancelled && (row.allocations || row.data?.allocations || []).some(a => a.document_id === record.id));
  const trail = Array.isArray(record.document_trail) ? record.document_trail : null;
  const stock = ['stock_opening','stock_adjustment'].includes(record.kind);
  const invoice = ['sales_invoice', 'purchase_bill', 'pos'].includes(record.kind);
  const hasBalance = invoice && record.posted && !cancelled;
  const balanceKnown = record.outstanding !== undefined && record.outstanding !== null && Number.isFinite(Number(record.outstanding));
  const available = record.data?.is_advance ? record.advance_remaining : ['credit_note', 'debit_note'].includes(record.kind) ? record.credit_remaining : undefined;
  return <div className="overlay detail-overlay" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="modal transaction-detail" role="dialog" aria-modal="true" aria-labelledby="transaction-detail-title">
      <header className="detail-heading">
        <div className="detail-type-icon"><FileText size={23} /></div>
        <div><span className="workspace-kicker">{labels[record.kind] || (record.kind || 'transaction').replaceAll('_', ' ')}</span><h2 id="transaction-detail-title">{record.number || 'Transaction details'}</h2><p>{company?.name} · Read-only overview</p></div>
        <button className="icon-button" aria-label="Close" disabled={locked} onClick={onClose}><X size={21} /></button>
      </header>
      <div className="detail-body" aria-busy={loading || cancelBusy}>
        <div className="detail-status-line"><span className={`status-badge ${cancelled ? 'cancelled' : record.posted || record.converted_to ? 'posted' : 'draft'}`}>{record.posted ? <CheckCircle2 size={14} /> : <Clock3 size={14} />}{status}</span>{settlementLabel(record) && <span className="detail-settlement">{settlementLabel(record)}</span>}<span>{record.date}</span></div>
        <section className="detail-money"><div><span>{cancelled ? 'Original document total' : 'Document total'}</span><strong>{amount(record.amount)}</strong><small>{record.name || 'No party'}</small></div><div><span>{cancelled ? 'Accounting effect' : hasBalance ? 'Still outstanding' : available !== undefined ? 'Available balance' : 'Accounting effect'}</span><strong className={hasBalance && Number(record.outstanding) > 0 ? 'due' : ''}>{cancelled ? 'Reversed' : hasBalance ? balanceKnown ? amount(record.outstanding) : '—' : available !== undefined ? amount(available) : draft ? 'Not posted' : record.posted ? 'Posted' : 'None'}</strong><small>{cancelled ? 'No active balance from this document' : hasBalance ? !balanceKnown ? 'Refresh details to see the current balance' : record.data?.due_date ? `Due ${record.data.due_date}` : 'No due date set' : draft ? 'No stock, cash or revenue posted' : 'Server-confirmed status'}</small></div></section>
        {loading && <p className="info-box" role="status">Refreshing transaction details…</p>}
        {error && <div className="error banner" role="alert">{error}<button className="link" onClick={onRetry}>Try again</button></div>}
        <div className="detail-action-bar">
          {actions.map((action, index) => <button key={action.kind} className={`button ${index === 0 && action.kind.startsWith('payment') ? 'primary' : 'secondary'}`} disabled={loading || !!error || locked} onClick={() => onRelated(record, action.kind)}>{action.label}<ArrowRight size={15} /></button>)}
          {['estimate', 'proforma'].includes(record.kind) && !record.converted_to && !cancelled && writable && <button className="button secondary" disabled={loading || !!error || locked} onClick={() => onConvert(record, 'sales_order')}>Create sales order<ArrowRight size={15} /></button>}
          {draft && !record.converted_to && !cancelled && writable && <button className="button primary" disabled={loading || !!error || locked} onClick={() => onConvert(record)}>Convert to {record.kind === 'purchase_order' ? 'bill' : 'invoice'}<ArrowRight size={15} /></button>}
          {writable && cancellable && <button className="button danger-outline" disabled={loading || !!error || locked} onClick={() => { setCancelError(''); setCancelOpen(true); }}><X size={15} />Cancel document</button>}
          {pdf && <button className="button secondary" disabled={loading || locked} onClick={() => onPdf(record)}><Download size={16} />Download PDF</button>}
          {pdf && receiptKinds.has(record.kind) && features.includes('thermal_receipts') && <details className="row-menu receipt-menu"><summary className="button secondary" aria-label="Print thermal receipt"><Printer size={15} />Print receipt</summary><div className="row-menu-list">{[['thermal_80', '80 mm roll'], ['thermal_58', '58 mm roll']].map(([template, label]) => <button key={template} type="button" disabled={loading || locked} onClick={event => { event.currentTarget.closest('details').open = false; onPdf(record, template); }}>{label}</button>)}</div></details>}
          {shareable.has(record.kind) && !cancelled && <button className="button secondary whatsapp" disabled={loading || locked} onClick={() => openWhatsApp(false)}><MessageCircle size={15} />Share on WhatsApp</button>}
          {canRemind(record) && <button className="button secondary whatsapp" disabled={loading || locked} onClick={() => openWhatsApp(true)}><BellRing size={15} />Send reminder</button>}
          {writable && editable && !record.converted_to && <button className="button secondary" disabled={loading || !!error || locked} onClick={() => onEdit(record)}><Pencil size={15} />Edit details</button>}
        </div>
        {cancelled && <div className="info-box cancelled-note" role="status"><strong>Cancelled.</strong> {record.data?.cancelled?.reason || 'No reason recorded'}. The number {record.number} stays in your records; its ledger, stock and balance effects were reversed.</div>}
        {cancelOpen && <section className="cancel-panel" role="alertdialog" aria-labelledby="cancel-title">
          <h3 id="cancel-title">Cancel {record.number}?</h3>
          <p>This reverses its ledger entry{['sales_invoice','purchase_bill','pos','credit_note','debit_note'].includes(record.kind) ? ', returns its stock' : ''} and frees any balance it used. The number is kept and the action is recorded in the activity log. It cannot be undone; create a new document if you need to redo it.</p>
          <label>Reason (required)<input disabled={cancelBusy} value={cancelReason} maxLength={200} onChange={event => setCancelReason(event.target.value)} placeholder="e.g. Entered twice" autoFocus /></label>
          {cancelError && <div className="error banner" role="alert">{cancelError}</div>}
          <div className="cancel-actions"><button className="button secondary" disabled={cancelBusy} onClick={() => setCancelOpen(false)}>Keep document</button><button className="button danger" disabled={cancelBusy || cancelReason.trim().length < 3} onClick={confirmCancel}>{cancelBusy ? 'Cancelling…' : 'Cancel document'}</button></div>
        </section>}
        {!writable && <p className="detail-caption">You have read-only access. You can inspect this transaction and download its document.</p>}
        {lines.length > 0 && <section className="detail-section"><div className="detail-section-heading"><h3>Items & services</h3><span>{lines.length} line{lines.length !== 1 ? 's' : ''}</span></div><div className="detail-lines">{lines.map((line, index) => <div className="detail-line" key={index}><span className="detail-line-number">{index + 1}</span><div><strong>{line.description}</strong><small>{line.quantity} {line.unit || 'units'} × {amount(line.rate)}{Number(line.gst_rate) > 0 ? ` · GST ${line.gst_rate}%` : ''}</small>{Object.hasOwn(line, 'discount_amount') ? <small>Line discount: {amount(line.discount_amount)}</small> : Number(line.discount_percent) > 0 ? <small>Line discount: {line.discount_percent}%</small> : null}{Number(line.document_discount) > 0 && <small>Document discount allocation: {amount(line.document_discount)}</small>}{line.hsn && <small>HSN/SAC {line.hsn}</small>}</div><strong>{amount(Number(line.taxable ?? Number(line.quantity) * Number(line.rate)) + Number(line.tax || 0))}</strong></div>)}</div></section>}
        <DocumentAmounts record={record} />
        {stock ? <StockRecordSummary record={record} /> : <section className="detail-section"><h3>Payment & document trail</h3>{trail !== null ? <>{trail.map(target => <button className="detail-trail-row" key={target.id} disabled={loading || locked} onClick={() => onOpen({id:target.id})}><FileText size={18} /><span><small>{target.relations.join(' · ')} · {target.date}</small><strong>{target.number || labels[target.kind] || target.kind} · {target.name}</strong><small>{labels[target.kind] || target.kind.replaceAll('_',' ')}{target.cancelled ? ' · Cancelled' : ''}</small></span><span><strong>{amount(target.allocated_amount ?? target.historical_allocated_amount ?? target.amount)}</strong><small>{target.allocated_amount != null ? 'Allocated amount' : target.historical_allocated_amount != null ? 'Cancelled allocation' : 'Document total'}</small></span></button>)}{!trail.length && <p className="detail-caption">No linked document or settlement is recorded.</p>}</> : <>{links.map(([title, id]) => { const target = records.find(row => row.id === id); return <button className="detail-trail-row" key={title + id} onClick={() => onOpen(target || { id })}><FileText size={18} /><span><small>{title}</small><strong>{target?.number || 'View linked document'}</strong></span><ArrowRight size={17} /></button>; })}{allocations.map((allocation, index) => { const target = records.find(row => row.id === allocation.document_id); return <button className="detail-trail-row" key={index} onClick={() => onOpen(target || { id: allocation.document_id })}><CheckCircle2 size={18} /><span><small>Allocated to</small><strong>{target?.number || 'View invoice or bill'}</strong></span><strong>{amount(allocation.amount)}</strong></button>; })}{paidAgainst.map(row => <button className="detail-trail-row" key={row.id} onClick={() => onOpen(row)}><CheckCircle2 size={18} /><span><small>{row.date} · {labels[row.kind] || row.kind}</small><strong>{row.number || 'View payment'}</strong></span><strong>{amount((row.allocations || row.data?.allocations || []).filter(a => a.document_id === record.id).reduce((sum, a) => sum + Number(a.amount), 0))}</strong></button>)}{!links.length && !allocations.length && !paidAgainst.length && <p className="detail-caption">{draft ? 'Convert this draft after review. The source and destination will remain linked here.' : 'No linked payment or conversion appears in this record.'}</p>}</>}<p className="detail-footnote">Recording a payment, settling an invoice and matching a bank statement are separate steps. Downloading or printing never posts another transaction.</p></section>}
        {features.includes('document_attachments') && api && ['purchase_bill', 'expense'].includes(record.kind) && <DocumentAttachments key={`${company.id}:${record.id}`} companyId={company.id} recordId={record.id} role={company.role} api={api} onLockChange={setAttachmentLocked} />}
        {writable && !cancelled && record.posted && ['credit_note','debit_note'].includes(record.kind) && Number(record.credit_remaining) > 0 && onManageCredits && <section className="detail-section"><h3>Use available credit</h3><p>Apply the remaining credit to an eligible document or record a refund in the existing {record.kind === 'debit_note' ? 'Payment out' : 'Payment in'} workspace. Select this note there; opening the workspace does not post anything.</p><button className="button secondary" disabled={loading || !!error || locked} onClick={() => onManageCredits(record)}>Open {record.kind === 'debit_note' ? 'supplier' : 'customer'} credits and refunds</button></section>}
        {record.data?.notes && <section className="detail-section"><h3>Notes</h3><p className="detail-notes">{record.data.notes}</p></section>}
      </div>
      <footer className="detail-footer"><span><CheckCircle2 size={15} />Your original record stays in history</span><button className="button secondary" disabled={locked} onClick={onClose}>Back to register</button></footer>
    </section>
  </div>;
}
