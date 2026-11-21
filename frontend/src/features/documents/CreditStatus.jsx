import React, { useEffect, useState } from 'react';
const money = value => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(Number(value || 0));
/** Advisory only: server canonical balances, debounced and scoped to this party. */
export default function CreditStatus({ api, companyId, partyId, asOf, proposedAmount = '0', compact = false }) {
  const [status, setStatus] = useState(null), [error, setError] = useState(''), [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true; setStatus(null); setError('');
    if (!partyId || !asOf) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      const query = new URLSearchParams({ as_of: asOf, proposed_amount: String(proposedAmount || '0') });
      api(`/companies/${companyId}/parties/${partyId}/credit-status?${query}`, { signal: controller.signal })
        .then(result => { if (active) setStatus(result); })
        .catch(reason => { if (active && reason.name !== 'AbortError') setError(reason.message); });
    }, 300);
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [companyId, partyId, asOf, proposedAmount, retry]);
  if (!partyId || !asOf) return null;
  if (error) return <p className="info-box full">Credit review unavailable: {error}. This advisory does not block saving; review the party statement before extending credit. <button type="button" className="button secondary" onClick={() => setRetry(value => value + 1)}>Retry credit review</button></p>;
  if (!status) return <p className="detail-caption full" role="status">Reviewing customer credit exposure…</p>;
  return <section className={`credit-status full ${status.exceeded ? 'credit-limit-warning' : ''}`} aria-label="Customer credit review" role="status">
    <div><strong>{status.exceeded ? 'Credit limit would be exceeded' : 'Customer credit review'}</strong><small>As of {status.as_of} · advisory only, saving is not blocked</small></div>
    <dl><div><dt>Credit limit</dt><dd>{status.credit_limit == null ? 'Not set' : money(status.credit_limit)}</dd></div><div><dt>Current net exposure</dt><dd>{money(status.current_exposure)}</dd></div>{Number(proposedAmount) > 0 && <div><dt>With this new sale</dt><dd>{money(status.projected_exposure)}</dd></div>}{status.remaining_credit != null && <div><dt>Remaining credit</dt><dd>{money(status.remaining_credit)}</dd></div>}</dl>
    {!compact && <p>Receivables {money(status.receivable)} less unused customer credits {money(status.customer_credit)} and advances {money(status.customer_advance)}. Supplier payables are not offset.</p>}
    {compact && <small>Net exposure deducts unused customer credits and advances; supplier payables are not offset. This is not a reservation or payment authorization.</small>}
  </section>;
}
