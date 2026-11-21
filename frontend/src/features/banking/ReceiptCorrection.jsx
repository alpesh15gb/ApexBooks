import React, { useEffect, useState } from 'react';
import { businessDate } from '../../businessDate.js';
import { usePostingRequest, pendingPostingMessage } from '../../usePostingRequest.js';
import { BalanceRefreshNotice, useBalanceRefresh } from '../../postingRefresh.jsx';
import { ledgerDate } from '../../ledgerFormat.js';

const money = value => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(value);
const purposes = { invoice: 'Invoice payment', goods: 'Goods advance', services: 'Service advance',
  advance: 'Advance', unallocated: 'Unallocated customer receipt' };
const creditLabel = credit => [ledgerDate(credit.date), credit.bank, credit.utr && `UTR ${credit.utr}`, money(credit.amount),
  credit.description].filter(Boolean).join(' · ');
const emptyPlan = credit_id => ({ credit_id, replace: [], unlink: [], allocations: [], apply: [] });
const amountProps = { type: 'number', min: '0.01', step: '0.01', required: true };
const gstTotal = tax => Object.values(tax).reduce((total, value) => total + Math.round(Number(value) * 100), 0) / 100;

function AllocationSummary({ receipt, includeNumber = true }) {
  return <>
    <strong>{purposes[receipt.purpose]} · {money(receipt.amount)}</strong>
    {includeNumber && <span> · {receipt.number}</span>}
    {receipt.advance_available !== null && <small> · {money(receipt.advance_available)} advance available</small>}
    {gstTotal(receipt.gst) > 0 && <small> · {money(gstTotal(receipt.gst))} advance GST</small>}
    {receipt.notes && <div>{receipt.notes}</div>}
    {receipt.direct.map(link => <div key={link.document_id}>{link.invoice} · {money(link.amount)}</div>)}
    {receipt.settlements.map(row => <div key={row.id}>{row.kind === 'advance_refund' ? 'Refund' : row.allocations.map(link => link.invoice).join(', ')}
      {' · '}{money(row.amount)} · {ledgerDate(row.date)}
      {gstTotal(row.gst) > 0 && <small> · {money(gstTotal(row.gst))} GST adjustment</small>}</div>)}
  </>;
}

function CreditPreview({ preview }) {
  return <section className="detail-section" aria-label="Correction preview">
    <h3>Correction preview</h3>
    <div className="table-wrap"><table>
      <thead><tr><th>Bank credit</th><th>Before</th><th>Proposed</th></tr></thead>
      <tbody>{preview.before.map((old, index) => {
        const next = preview.after[index];
        const oldIds = new Set(old.receipts.map(row => row.id));
        return <tr key={old.id}>
          <th scope="row">{creditLabel(old)}</th>
          {[old, next].map((credit, column) => <td key={column}>
            <p>Booked {money(credit.booked)} · Unallocated {money(credit.unallocated)}</p>
            {credit.receipts.map(row => <div className="line-card" key={row.id}><AllocationSummary receipt={row} includeNumber={oldIds.has(row.id)} /></div>)}
          </td>)}
        </tr>;
      })}</tbody>
    </table></div>
    {!!preview.invoices_before.length && <div className="table-wrap"><table>
      <thead><tr><th>Invoice</th><th>Outstanding before</th><th>Outstanding after</th></tr></thead>
      <tbody>{preview.invoices_before.map((invoice, index) => <tr key={invoice.id}>
        <th scope="row">{invoice.number}</th><td>{money(invoice.outstanding)}</td><td>{money(preview.invoices_after[index].outstanding)}</td>
      </tr>)}</tbody>
    </table></div>}
  </section>;
}

function PlanFields({ credit, plan, invoices, update, remove, company }) {
  const advanceSources = credit.receipts.filter(row => row.advance_available !== null && !plan.replace.includes(row.id));
  const booked = credit.receipts.filter(row => !plan.replace.includes(row.id)).reduce((sum, row) => sum + Math.round(Number(row.amount) * 100), 0);
  const proposed = plan.allocations.reduce((sum, row) => sum + Math.round(Number(row.amount || 0) * 100), 0);
  const left = (Math.round(Number(credit.amount) * 100) - booked - proposed) / 100;
  function toggle(field, id, checked) {
    update({ [field]: checked ? [...plan[field], id] : plan[field].filter(value => value !== id) });
  }
  function editRow(field, id, change) {
    update({ [field]: plan[field].map(row => row.key === id ? { ...row, ...change } : row) });
  }
  const removeRow = (field, id) => update({ [field]: plan[field].filter(row => row.key !== id) });
  return <section className="detail-section" aria-label={creditLabel(credit)}>
    <h3>{creditLabel(credit)}</h3>
    <p>Booked {money(credit.booked)} · Currently unallocated {money(credit.unallocated)}</p>
    {credit.receipts.map(receipt => <section key={receipt.id} className="line-card">
      <AllocationSummary receipt={receipt}/>
      <label><input type="checkbox" checked={plan.replace.includes(receipt.id)}
        onChange={event => toggle('replace', receipt.id, event.target.checked)}/> Reclassify {receipt.number}</label>
      {receipt.settlements.filter(row => row.kind === 'advance_application').map(row => <label key={row.id}>
        <input type="checkbox" checked={plan.unlink.includes(row.id)}
          onChange={event => toggle('unlink', row.id, event.target.checked)}/>
        {' '}Unlink {row.number} · {row.allocations.map(link => link.invoice).join(', ')} · {money(row.amount)}
      </label>)}
    </section>)}
    {plan.allocations.map(row => <div key={row.key} className="form-grid line-card">
      <label>Purpose<select aria-label="Purpose" value={row.purpose} onChange={event => editRow('allocations', row.key,
        { purpose: event.target.value, document_id: '' })}>
        <option value="invoice">Invoice payment</option><option value="goods">Goods advance</option><option value="services">Service advance</option>
      </select></label>
      <label>Allocation amount<input {...amountProps} value={row.amount} onChange={event => editRow('allocations', row.key, { amount: event.target.value })}/></label>
      {row.purpose === 'invoice' ? <label>Invoice<select aria-label="Invoice" required value={row.document_id}
        onChange={event => editRow('allocations', row.key, { document_id: event.target.value })}>
        <option value="">Choose invoice</option>{invoices.map(invoice => <option key={invoice.id} value={invoice.id}>{invoice.number} · {money(invoice.outstanding)} outstanding</option>)}
      </select></label> : <label>Advance description<input maxLength={500} value={row.notes}
        onChange={event => editRow('allocations', row.key, { notes: event.target.value })}/></label>}
      {row.purpose === 'services' && <>
        <label>GST rate (%)<input type="number" required min="0" max="100" step="0.01" value={row.gst_rate}
          onChange={event => editRow('allocations', row.key, { gst_rate: event.target.value })}/></label>
        <label>Place of supply code<input required inputMode="numeric" pattern="[0-9]{2}" maxLength={2} value={row.place_of_supply}
          onChange={event => editRow('allocations', row.key, { place_of_supply: event.target.value })}/></label>
      </>}
      <button type="button" className="button secondary" onClick={() => removeRow('allocations', row.key)}>Remove allocation</button>
    </div>)}
    {plan.apply.map(row => <div key={row.key} className="form-grid line-card">
      <label>Existing advance<select aria-label="Existing advance" required value={row.source_id} onChange={event => editRow('apply', row.key, { source_id: event.target.value })}>
        <option value="">Choose advance</option>{advanceSources.map(source => <option key={source.id} value={source.id}>{source.number} · {money(source.amount)}</option>)}
      </select></label>
      <label>Apply to invoice<select aria-label="Apply to invoice" required value={row.document_id} onChange={event => editRow('apply', row.key, { document_id: event.target.value })}>
        <option value="">Choose invoice</option>{invoices.filter(invoice => invoice.kind === 'sales_invoice').map(invoice =>
          <option key={invoice.id} value={invoice.id}>{invoice.number} · {money(invoice.outstanding)} outstanding</option>)}
      </select></label>
      <label>Application date<input type="date" min={credit.date} required value={row.date} onChange={event => editRow('apply', row.key, { date: event.target.value })}/></label>
      <label>Application amount<input {...amountProps} value={row.amount} onChange={event => editRow('apply', row.key, { amount: event.target.value })}/></label>
      <button type="button" className="button secondary" onClick={() => removeRow('apply', row.key)}>Remove application</button>
    </div>)}
    <p>{left < 0 ? `Allocations exceed the credit by ${money(-left)}` : `New unallocated remainder ${money(left)}`}</p>
    <div className="detail-action-bar">
      <button type="button" className="button secondary" onClick={() => update({ allocations: [...plan.allocations,
        { key: crypto.randomUUID(), purpose: 'invoice', amount: '', document_id: '', gst_rate: '', place_of_supply: company.state_code || '', notes: '' }] })}>Add allocation</button>
      {advanceSources.length > 0 && <button type="button" className="button secondary" onClick={() => update({ apply: [...plan.apply,
        { key: crypto.randomUUID(), source_id: '', document_id: '', amount: '', date: businessDate() }] })}>Apply existing advance</button>}
      {remove && <button type="button" className="button secondary" onClick={remove}>Remove credit</button>}
    </div>
  </section>;
}

export default function ReceiptCorrection({ record, company, api, close, refresh, done }) {
  const [context, setContext] = useState(null);
  const [plans, setPlans] = useState([]);
  const [reason, setReason] = useState('');
  const [credit, setCredit] = useState('');
  const [preview, setPreview] = useState(null);
  const [posted, setPosted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  // The post endpoint checks the stored outcome before returning a validation conflict.
  const posting = usePostingRequest({ definitiveRetryStatuses: [409, 422] });
  const balanceRefresh = useBalanceRefresh(refresh);
  const path = `/companies/${company.id}/records/${record.id}/receipt-correction`;
  const locked = posting.busy || posting.pending || balanceRefresh.busy;
  useEffect(() => {
    let live = true;
    api(path).then(data => {
      if (!live) return;
      setContext(data);
      const anchor = emptyPlan(data.anchor_credit_id);
      if (record.kind === 'advance_application') anchor.unlink = [record.id];
      setPlans([anchor]);
    }).catch(problem => { if (live) setError(problem.message); });
    return () => { live = false; };
  }, [api, path, record.id, record.kind]);

  async function review(event) {
    event.preventDefault();
    setError('');
    setLoading(true);
    const payload = { reason, credits: plans.map(plan => ({
      ...plan,
      allocations: plan.allocations.map(({ purpose, amount, document_id, gst_rate, place_of_supply, notes }) => ({
        purpose, amount, document_id: document_id || null, notes,
        ...(purpose === 'services' ? { gst_rate, place_of_supply } : {}),
      })),
      apply: plan.apply.map(({ source_id, document_id, date, amount }) => ({ source_id, document_id, date, amount })),
    })) };
    try {
      const result = await api(path + '/preview', { method: 'POST', body: JSON.stringify(payload) });
      setPreview({ result, key: crypto.randomUUID(), body: JSON.stringify({ ...payload, snapshot: result.snapshot }) });
    } catch (problem) { setError(problem.message); }
    finally { setLoading(false); }
  }

  async function post() {
    setError('');
    try {
      const response = await posting.run(() => api(path + '/post', {
        method: 'POST', headers: { 'Idempotency-Key': preview.key }, body: preview.body,
      }));
      if (!response) return;
      setPosted(true);
      await balanceRefresh.run();
    } catch (problem) { setError(problem.message); }
  }

  return <div className="overlay detail-overlay">
    <section className="modal transaction-detail" role="dialog" aria-modal="true" aria-labelledby="receipt-correction-heading">
      <header className="detail-heading"><div><h2 id="receipt-correction-heading">Correct allocation</h2>
        <p>{record.name} · {record.number}</p></div>
        <button className="button secondary" disabled={locked || loading} onClick={posted ? done : close}>Close correction</button>
      </header>
      <div className="detail-body" aria-busy={locked || loading}>
        {error && <p className="error" role="alert">{error}</p>}
        {posting.pending && !posting.busy && <p className="info-box" role="status">{pendingPostingMessage}</p>}
        {posted && <p role="status">Receipt allocation corrected.</p>}
        <BalanceRefreshNotice state={balanceRefresh}/>
        {preview && <CreditPreview preview={preview.result}/>}
        {preview && !posted && <div className="detail-action-bar">
          <button type="button" className="button secondary" disabled={locked}
            onClick={() => { setPreview(null); setError(''); }}>Edit correction</button>
          <button type="button" className="button primary" disabled={posting.busy} onClick={post}>
            {posting.pending ? 'Retry correction' : 'Post correction'}
          </button>
        </div>}
        {!context && !error && <p role="status">Loading bank credits and allocations…</p>}
        {context && !preview && <form onSubmit={review}>
          <fieldset className="submission-fields" disabled={loading}>
            {plans.map(plan => <PlanFields key={plan.credit_id} plan={plan} invoices={context.invoices} company={company}
              credit={context.credits.find(row => row.id === plan.credit_id)}
              update={change => setPlans(current => current.map(row => row.credit_id === plan.credit_id ? { ...row, ...change } : row))}
              remove={plan.credit_id === context.anchor_credit_id ? undefined : () => setPlans(current => current.filter(row => row.credit_id !== plan.credit_id))}/>)}
            <div className="form-grid detail-section">
              <label>Another bank credit or receipt<select aria-label="Another bank credit or receipt" value={credit} onChange={event => setCredit(event.target.value)}>
                <option value="">Choose bank credit or receipt</option>
                {context.credits.filter(row => !plans.some(plan => plan.credit_id === row.id)).map(row =>
                  <option key={row.id} value={row.id}>{creditLabel(row)}</option>)}
              </select></label>
              <button type="button" className="button secondary" disabled={!credit}
                onClick={() => { setPlans([...plans, emptyPlan(credit)]); setCredit(''); }}>Add credit</button>
              <label className="full">Correction reason<textarea required minLength={3} maxLength={200}
                value={reason} onChange={event => setReason(event.target.value)}/></label>
              <button className="button primary" type="submit">{loading ? 'Preparing preview…' : 'Preview correction'}</button>
            </div>
          </fieldset>
        </form>}
      </div>
    </section>
  </div>;
}
