import React from 'react';
import { ArrowRight, CheckCircle2, Clock3, Download, FileText, Pencil, X } from 'lucide-react';
import { relatedRecordActions, settlementLabel } from './recordLifecycle.js';
const drafts = new Set(['estimate', 'proforma', 'sales_order', 'purchase_order']);
const amount = value => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(value || 0));

export default function TransactionDetail({ record, records, company, labels, loading, error, onClose, onRetry, onEdit, onRelated, onConvert, onPdf, onOpen }) {
  const writable = ['owner', 'editor'].includes(company?.role);
  const draft = drafts.has(record.kind);
  const status = record.converted_to ? 'Converted' : draft ? 'Open draft' : record.posted ? 'Posted' : 'Unposted';
  const actions = relatedRecordActions(record, writable);
  const editable = ['sales_invoice','purchase_bill','pos','expense','credit_note','debit_note','payment_in','payment_out','bank_transfer'].includes(record.kind) || draft;
  const pdf = ['sales_invoice','purchase_bill','pos','expense','credit_note','debit_note','payment_in','payment_out','customer_refund','supplier_refund','advance_refund'].includes(record.kind) || draft;
  const lines = record.data?.lines || [];
  const links = [
    ['Created from', record.data?.source_document_id],
    ['Converted to', record.converted_to],
    ['Original document', record.data?.applied_to],
  ].filter(([, id]) => id && id !== 'source-converted');
  const allocations = record.allocations || record.data?.allocations || [];
  const paidAgainst = records.filter(row => row.id !== record.id && (row.allocations || row.data?.allocations || []).some(a => a.document_id === record.id));
  const invoice = ['sales_invoice', 'purchase_bill', 'pos'].includes(record.kind);
  const hasBalance = invoice && record.posted;
  const available = record.data?.is_advance ? record.advance_remaining : ['credit_note', 'debit_note'].includes(record.kind) ? record.credit_remaining : undefined;
  return <div className="overlay detail-overlay" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="modal transaction-detail" role="dialog" aria-modal="true" aria-labelledby="transaction-detail-title">
      <header className="detail-heading">
        <div className="detail-type-icon"><FileText size={23} /></div>
        <div><span className="workspace-kicker">{labels[record.kind] || (record.kind || 'transaction').replaceAll('_', ' ')}</span><h2 id="transaction-detail-title">{record.number || 'Transaction details'}</h2><p>{company?.name} · Read-only overview</p></div>
        <button className="icon-button" aria-label="Close" onClick={onClose}><X size={21} /></button>
      </header>
      <div className="detail-body" aria-busy={loading}>
        <div className="detail-status-line"><span className={`status-badge ${record.posted || record.converted_to ? 'posted' : 'draft'}`}>{record.posted ? <CheckCircle2 size={14} /> : <Clock3 size={14} />}{status}</span>{settlementLabel(record) && <span className="detail-settlement">{settlementLabel(record)}</span>}<span>{record.date}</span></div>
        <section className="detail-money"><div><span>Document total</span><strong>{amount(record.amount)}</strong><small>{record.name || 'No party'}</small></div><div><span>{hasBalance ? 'Still outstanding' : available !== undefined ? 'Available balance' : 'Accounting effect'}</span><strong className={hasBalance && Number(record.outstanding) > 0 ? 'due' : ''}>{hasBalance ? amount(record.outstanding) : available !== undefined ? amount(available) : draft ? 'Not posted' : record.posted ? 'Posted' : 'None'}</strong><small>{hasBalance ? record.data?.due_date ? `Due ${record.data.due_date}` : 'No due date set' : draft ? 'No stock, cash or revenue posted' : 'Server-confirmed status'}</small></div></section>
        {loading && <p className="info-box" role="status">Refreshing transaction details…</p>}
        {error && <div className="error banner" role="alert">{error}<button className="link" onClick={onRetry}>Try again</button></div>}
        <div className="detail-action-bar">
          {actions.map((action, index) => <button key={action.kind} className={`button ${index === 0 && action.kind.startsWith('payment') ? 'primary' : 'secondary'}`} disabled={loading || !!error} onClick={() => onRelated(record, action.kind)}>{action.label}<ArrowRight size={15} /></button>)}
          {['estimate', 'proforma'].includes(record.kind) && !record.converted_to && writable && <button className="button secondary" disabled={loading || !!error} onClick={() => onConvert(record, 'sales_order')}>Create sales order<ArrowRight size={15} /></button>}
          {draft && !record.converted_to && writable && <button className="button primary" disabled={loading || !!error} onClick={() => onConvert(record)}>Convert to {record.kind === 'purchase_order' ? 'bill' : 'invoice'}<ArrowRight size={15} /></button>}
          {pdf && <button className="button secondary" disabled={loading} onClick={() => onPdf(record)}><Download size={16} />Download PDF</button>}
          {writable && editable && !record.converted_to && <button className="button secondary" disabled={loading || !!error} onClick={() => onEdit(record)}><Pencil size={15} />Edit details</button>}
        </div>
        {!writable && <p className="detail-caption">You have read-only access. You can inspect this transaction and download its document.</p>}
        {lines.length > 0 && <section className="detail-section"><div className="detail-section-heading"><h3>Items & services</h3><span>{lines.length} line{lines.length !== 1 ? 's' : ''}</span></div><div className="detail-lines">{lines.map((line, index) => <div className="detail-line" key={index}><span className="detail-line-number">{index + 1}</span><div><strong>{line.description}</strong><small>{line.quantity} {line.unit || 'units'} × {amount(line.rate)}{Number(line.gst_rate) > 0 ? ` · GST ${line.gst_rate}%` : ''}</small>{line.hsn && <small>HSN/SAC {line.hsn}</small>}</div><strong>{amount(Number(line.taxable ?? Number(line.quantity) * Number(line.rate)) + Number(line.tax || 0))}</strong></div>)}</div></section>}
        <section className="detail-section"><h3>Payment & document trail</h3>{links.map(([title, id]) => { const target = records.find(row => row.id === id); return <button className="detail-trail-row" key={title + id} onClick={() => onOpen(target || { id })}><FileText size={18} /><span><small>{title}</small><strong>{target?.number || 'View linked document'}</strong></span><ArrowRight size={17} /></button>; })}{allocations.map((allocation, index) => { const target = records.find(row => row.id === allocation.document_id); return <button className="detail-trail-row" key={index} onClick={() => onOpen(target || { id: allocation.document_id })}><CheckCircle2 size={18} /><span><small>Allocated to</small><strong>{target?.number || 'View invoice or bill'}</strong></span><strong>{amount(allocation.amount)}</strong></button>; })}{paidAgainst.map(row => <button className="detail-trail-row" key={row.id} onClick={() => onOpen(row)}><CheckCircle2 size={18} /><span><small>{row.date} · {labels[row.kind] || row.kind}</small><strong>{row.number || 'View payment'}</strong></span><strong>{amount((row.allocations || row.data?.allocations || []).filter(a => a.document_id === record.id).reduce((sum, a) => sum + Number(a.amount), 0))}</strong></button>)}{!links.length && !allocations.length && !paidAgainst.length && <p className="detail-caption">{draft ? 'Convert this draft after review. The source and destination will remain linked here.' : 'No linked payment or conversion appears in this record.'}</p>}<p className="detail-footnote">Recording a payment, settling an invoice and matching a bank statement are separate steps. Downloading or printing never posts another transaction.</p></section>
        {record.data?.notes && <section className="detail-section"><h3>Notes</h3><p className="detail-notes">{record.data.notes}</p></section>}
      </div>
      <footer className="detail-footer"><span><CheckCircle2 size={15} />Your original record stays in history</span><button className="button secondary" onClick={onClose}>Back to register</button></footer>
    </section>
  </div>;
}
