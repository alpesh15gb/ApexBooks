import React, { useEffect, useId, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { BUSINESS_TIME_ZONE } from './businessDate.js';
import { usePostingRequest, pendingPostingMessage } from './usePostingRequest.js';
import { formatRegisterMoney, parseRegisterMoney } from './posRegisterSummary.js';

const dateTime = new Intl.DateTimeFormat('en-IN', {
  timeZone: BUSINESS_TIME_ZONE, dateStyle: 'medium', timeStyle: 'short',
});
const paise = value => BigInt(value.replace('.', ''));
const money = value => formatRegisterMoney(paise(value));

function TenderTotals({ totals }) {
  return (
    <div className="pos-reconciliation-results">
      <div><span>Expected cash</span><strong>{money(totals.expected_cash)}</strong></div>
      <div><span>Cash sales</span><strong>{money(totals.cash_sales)}</strong></div>
      <div><span>Cash refunds</span><strong>{money(totals.cash_refunds)}</strong></div>
      <div><span>Bank / UPI / card net</span><strong>{formatRegisterMoney(
        paise(totals.bank_sales) - paise(totals.bank_refunds),
      )}</strong></div>
      <div><span>Other cash added</span><strong>{money(totals.cash_in)}</strong></div>
      <div><span>Other cash removed</span><strong>{money(totals.cash_out)}</strong></div>
    </div>
  );
}

function CashActivity({ movements, count }) {
  if (!movements.length) return <p>No cash additions or drops.</p>;
  return (
    <div className="pos-register-activity">
      {count > movements.length && <p>Showing the latest {movements.length} of {count} movements.</p>}
      <ul>
        {movements.map(row => (
          <li key={row.id}>
            <strong>{row.data.direction === 'in' ? 'Added' : 'Removed'} {money(row.amount)}</strong>
            <span>{row.data.reason} · {row.data.actor} · {dateTime.format(new Date(row.data.created_at))}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ClosedRegister({ row, base, api }) {
  const [history, setHistory] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const data = row.data;
  async function loadDetails() {
    setLoading(true);
    setError('');
    try { setHistory(await api(`${base}/${row.id}`)); }
    catch (error) { setError(error.message); }
    finally { setLoading(false); }
  }
  return (
    <details className="pos-register-closed">
      <summary>{dateTime.format(new Date(data.closed_at))} · Counted {money(data.counted_cash)} · Variance {money(data.variance)}</summary>
      <p>Opened by {data.opened_by} with {money(data.opening_float)} · Closed by {data.closed_by}</p>
      {data.close_reason && <p>{data.close_reason}</p>}
      <TenderTotals totals={data.closed_totals} />
      {history
        ? <CashActivity movements={history.movements} count={data.closed_totals.movement_count} />
        : <button type="button" className="button secondary" disabled={loading} onClick={loadDetails}>{loading ? 'Loading…' : 'View cash activity'}</button>}
      {error && <p className="error" role="alert">{error}</p>}
    </details>
  );
}

const emptyCash = { direction: 'in', amount: '', reason: '' };

export default function PosRegisterSession({ companyId, canWrite, records, api }) {
  const movementKindId = useId();
  const [state, setState] = useState(null);
  const [revision, setRevision] = useState(0);
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [opening, setOpening] = useState('');
  const [cash, setCash] = useState(emptyCash);
  const [counted, setCounted] = useState('');
  const [closeReason, setCloseReason] = useState('');
  const [action, setAction] = useState('');
  const posting = usePostingRequest({ definitiveRetryStatuses: [409] });
  const { busy, pending } = posting;
  const base = `/companies/${companyId}/pos-register`;
  const active = state?.active;
  const countedPaise = parseRegisterMoney(counted);
  const difference = active && countedPaise !== null ? countedPaise - paise(active.totals.expected_cash) : null;
  const reasonRequired = difference !== null && difference !== 0n;

  useEffect(() => {
    const request = new AbortController();
    api(base, { signal: request.signal })
      .then(current => {
        if (!request.signal.aborted) {
          setState(current);
          setLoadError('');
        }
      })
      .catch(error => { if (!request.signal.aborted) setLoadError(error.message); });
    return () => request.abort();
  }, [api, base, records, revision]);

  function reload() {
    setState(null);
    setLoadError('');
    setRevision(current => current + 1);
  }

  async function save(next, path, body) {
    if (busy) return;
    setActionError('');
    setAction(next);
    const options = path ? {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify(body),
    } : null;
    try {
      const result = await posting.run(() => api(path, options));
      if (!result) return;
      setOpening('');
      setCash(emptyCash);
      setCounted('');
      setCloseReason('');
      reload();
    } catch (error) {
      setActionError(error.message);
      if (error.status === 409 && !posting.isPending()) reload();
    }
  }

  const actionLabel = { open: 'Open register', movement: 'Record cash movement', close: 'Close register' };
  function submit(event, next, path, body) {
    event.preventDefault();
    if (!pending) void save(next, path, body);
  }

  return (
    <section className="panel settings-panel pos-reconciliation pos-register-session" aria-label="POS register session">
      <header className="pos-reconciliation-heading">
        <div>
          <div className="pos-register-title">
            <h2>Register session</h2>
            {state && <span className={`status-badge pos-register-status${active ? ' posted' : ''}`}>{active ? 'Open' : 'Closed'}</span>}
          </div>
          <p>One shared drawer for this company. POS sales and linked refunds posted while it is open enter this session.</p>
        </div>
        <button type="button" className="button secondary" onClick={reload} disabled={busy || pending || (!state && !loadError)}>
          <RefreshCw size={16} aria-hidden="true" />Refresh register
        </button>
      </header>
      {loadError && <p className="error" role="alert">{loadError}</p>}
      {actionError && <p className="error" role="alert">{actionError}</p>}
      {!state && !loadError && <p role="status">Loading register…</p>}
      {pending && !busy && <div className="info-box">
        <p role="status">{pendingPostingMessage}</p>
        <button type="button" className="button secondary" onClick={() => save(action)}>Retry {actionLabel[action]?.toLowerCase()}</button>
      </div>}
      {state && !active && <>
        {canWrite && <form onSubmit={event => submit(event, 'open', base + '/open', { opening_float: opening })}>
          <fieldset className="form-grid submission-fields pos-reconciliation-count pos-register-fields" disabled={busy || pending || !!loadError}>
            <label>Opening float (₹)
              <input required inputMode="decimal" maxLength={16} value={opening} onChange={event => setOpening(event.target.value)} />
            </label>
            <button className="button primary" disabled={parseRegisterMoney(opening) === null}>{busy ? 'Opening…' : 'Open register'}</button>
          </fieldset>
        </form>}
      </>}
      {active && <>
        <p>Opened {dateTime.format(new Date(active.data.created_at))} by {active.data.opened_by} with {money(active.data.opening_float)}</p>
        <TenderTotals totals={active.totals} />
        <p>{active.totals.sales_count} {active.totals.sales_count === 1 ? 'sale' : 'sales'} · {active.totals.refund_count} linked {active.totals.refund_count === 1 ? 'refund' : 'refunds'} · {active.totals.movement_count} cash {active.totals.movement_count === 1 ? 'movement' : 'movements'}</p>
        <details>
          <summary>Cash activity</summary>
          <CashActivity movements={active.movements} count={active.totals.movement_count} />
        </details>
        {canWrite && <>
          <form onSubmit={event => submit(event, 'movement', `${base}/${active.id}/movements`, cash)}>
            <fieldset className="form-grid submission-fields pos-reconciliation-count pos-register-fields" disabled={busy || pending || !!loadError}>
              <legend>Record cash movement</legend>
              <div>
                <label htmlFor={movementKindId}>Movement</label>
                <select id={movementKindId} className="form-select" value={cash.direction} onChange={event => setCash({ ...cash, direction: event.target.value })}>
                  <option value="in">Add cash</option><option value="out">Remove cash</option>
                </select>
              </div>
              <label>Amount (₹)
                <input required inputMode="decimal" maxLength={16} value={cash.amount} onChange={event => setCash({ ...cash, amount: event.target.value })} />
              </label>
              <label className="full">Reason
                <input required maxLength={200} value={cash.reason} onChange={event => setCash({ ...cash, reason: event.target.value })} />
              </label>
              <p>Record drawer movements here and enter any accounting transaction separately.</p>
              <button className="button secondary" disabled={!(parseRegisterMoney(cash.amount) > 0n) || !cash.reason.trim()}>{busy && action === 'movement' ? 'Recording…' : 'Record cash movement'}</button>
            </fieldset>
          </form>
          <form onSubmit={event => submit(event, 'close', `${base}/${active.id}/close`, {
            counted_cash: counted, reason: closeReason, snapshot: active.snapshot,
          })}>
            <fieldset className="form-grid submission-fields pos-reconciliation-count pos-register-fields" disabled={busy || pending || !!loadError}>
              <legend>Close register</legend>
              <label>Counted cash (₹)
                <input required inputMode="decimal" maxLength={16} value={counted} onChange={event => setCounted(event.target.value)} />
              </label>
              <label>Reason for any difference
                <input required={reasonRequired} maxLength={200} value={closeReason} onChange={event => setCloseReason(event.target.value)} />
              </label>
              {difference !== null && <p className="full" role="status">
                {difference === 0n ? 'Cash count matches.' : `Cash ${difference < 0n ? 'short' : 'over'} by ${formatRegisterMoney(difference < 0n ? -difference : difference)}.`}
              </p>}
              <p>Closing saves the count and locks edits and cancellations for the session's sales.</p>
              <button className="button primary" disabled={countedPaise === null || (reasonRequired && !closeReason.trim())}>{busy && action === 'close' ? 'Closing…' : 'Close register'}</button>
            </fieldset>
          </form>
        </>}
      </>}
      {state?.closed.length > 0 && <section aria-label="Recent closed registers">
        <h3>Recent closes</h3>
        {state.closed.map(row => <ClosedRegister key={row.id} row={row} base={base} api={api} />)}
      </section>}
    </section>
  );
}
