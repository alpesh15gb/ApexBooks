import React, { useMemo, useState } from 'react';
import { Download, RefreshCw } from 'lucide-react';
import { businessDate } from './businessDate.js';
import { downloadBlob } from './downloadBlob.js';
import PosRegisterSession from './PosRegisterSession.jsx';
import {
  cashCountFields, formatRegisterMoney, posCloseCsv, reconcilePosCash, summarizePosDay,
} from './posRegisterSummary.js';

const displayMoney = value => value === null ? '—' : formatRegisterMoney(value);

export default function PosRegisterSummary({ records, refresh, companyName, companyId, api, canWrite, registerEnabled }) {
  const [date, setDate] = useState(businessDate);
  const [entries, setEntries] = useState({});
  const [action, setAction] = useState('');
  const [notice, setNotice] = useState(null);
  const day = useMemo(() => summarizePosDay(records, date), [records, date]);
  const reconciliation = reconcilePosCash(day, entries);
  const { expected, variance, invalidFields } = reconciliation;
  const dateValid = Boolean(date && date <= businessDate());
  const exporting = action === 'export';
  const busy = Boolean(action);

  function updateDate(value) {
    setDate(value);
    setEntries({});
    setNotice(null);
  }

  async function refreshDay(exporting) {
    setAction(exporting ? 'export' : 'refresh');
    setNotice(null);
    try {
      // The parent reloads company records from the API, including returns
      // whose source sale was posted before the selected day.
      const current = await refresh();
      if (!Array.isArray(current)) throw new Error('Could not refresh POS records. Try again.');
      if (!exporting) {
        setNotice({ message: 'Posted POS records refreshed.' });
        return;
      }
      const latest = summarizePosDay(current, date);
      const latestReconciliation = reconcilePosCash(latest, entries);
      const original = posCloseCsv({ companyName, date, day, reconciliation });
      if (latestReconciliation.variance === null ||
          posCloseCsv({ companyName, date, day: latest, reconciliation: latestReconciliation }) !== original) {
        setNotice({ error: true, message: 'Sales or refunds changed. Review the updated figures before exporting.' });
        return;
      }
      downloadBlob(new Blob([original], { type: 'text/csv;charset=utf-8' }), `apex-pos-reconciliation-${date}.csv`);
    } catch (error) {
      setNotice({ error: true, message: error.message || 'Could not refresh POS records.' });
    } finally {
      setAction('');
    }
  }

  const rows = [
    ['Cash', day.cashSales, day.cashRefunds],
    ['Bank / UPI / card', day.bankSales, day.bankRefunds],
  ];
  const varianceLabel = variance === null || variance === 0n ? 'Cash variance' : variance < 0n ? 'Cash short' : 'Cash over';

  const worksheet = (
    <section className={`settings-panel pos-reconciliation${registerEnabled ? '' : ' panel'}`} aria-label="Daily POS reconciliation">
      <header className="pos-reconciliation-heading">
        <div>
          <h2>Daily reconciliation</h2>
          <p>Review this company's posted POS sales and linked refunds for the business date across all sessions.</p>
        </div>
        <button type="button" className="button secondary" disabled={busy} onClick={() => refreshDay(false)}>
          <RefreshCw size={16} aria-hidden="true" />{action === 'refresh' ? 'Refreshing…' : 'Refresh POS records'}
        </button>
      </header>
      {notice && <p className={notice.error ? 'error' : 'info-box'} role={notice.error ? 'alert' : 'status'}>{notice.message}</p>}
      <label className="pos-reconciliation-date">
        Business date
        <input type="date" required max={businessDate()} value={date} disabled={busy} onChange={event => updateDate(event.target.value)} />
      </label>
      {!dateValid && <p className="error" role="alert">Choose today or an earlier business date.</p>}
      {dateValid && <>
        <div className="table-wrap pos-reconciliation-tenders">
          <table aria-label="Posted POS tenders">
            <thead>
              <tr><th scope="col">Tender</th><th scope="col" className="right">Sales</th><th scope="col" className="right">Refunds</th><th scope="col" className="right">Net</th></tr>
            </thead>
            <tbody>
              {rows.map(([label, sales, refunds]) => (
                <tr key={label}>
                  <th scope="row">{label}</th>
                  <td className="right">{formatRegisterMoney(sales)}</td>
                  <td className="right">{formatRegisterMoney(refunds)}</td>
                  <td className="right amount">{formatRegisterMoney(sales - refunds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>{day.saleCount} {day.saleCount === 1 ? 'sale' : 'sales'} · {day.refundCount} linked {day.refundCount === 1 ? 'refund' : 'refunds'}
          {day.cancelledCount > 0 && ` · ${day.cancelledCount} cancelled ${day.cancelledCount === 1 ? 'receipt' : 'receipts'} excluded`}</p>
        {day.unresolvedCount > 0 && <p className="error" role="alert">Review {day.unresolvedCount} posted POS sales or refunds with an unresolved tender before reconciling.</p>}
        <fieldset className="form-grid submission-fields pos-reconciliation-count" disabled={busy}>
          <legend>Drawer count</legend>
          <p className="full">Enter the opening float and cash counted. Use the other cash fields for movements outside the POS figures above, such as cash drops.</p>
          {cashCountFields.map(({ key, label, required }) => (
            <label key={key}>
              {label} (₹)
              <input
                inputMode="decimal"
                maxLength={16}
                required={required}
                aria-invalid={invalidFields.includes(key) || undefined}
                aria-describedby={invalidFields.includes(key) ? `pos-reconciliation-${key}-error` : undefined}
                value={entries[key] || ''}
                placeholder={required ? undefined : '0.00'}
                onChange={event => setEntries(current => ({ ...current, [key]: event.target.value }))}
              />
              {invalidFields.includes(key) && <span className="error" id={`pos-reconciliation-${key}-error`}>Enter a nonnegative amount with up to two decimal places.</span>}
            </label>
          ))}
        </fieldset>
        <div className="pos-reconciliation-results" aria-live="polite">
          <div><span>Expected cash</span><strong>{displayMoney(expected)}</strong></div>
          <div><span>{varianceLabel}</span><strong>{displayMoney(variance === null ? null : variance < 0n ? -variance : variance)}</strong></div>
        </div>
        <div className="pos-reconciliation-export">
          <p>Export the worksheet for your daily records. Record any accounting adjustment separately.</p>
          <button type="button" className="button secondary" disabled={busy || variance === null} onClick={() => refreshDay(true)}>
            <Download size={16} aria-hidden="true" />{exporting ? 'Checking POS records…' : 'Export count CSV'}
          </button>
        </div>
      </>}
    </section>
  );
  if (!registerEnabled) return worksheet;
  return <>
    <PosRegisterSession key={companyId} companyId={companyId} api={api} canWrite={canWrite} records={records} />
    <details className="panel pos-daily-disclosure">
      <summary>Daily totals and CSV export</summary>
      {worksheet}
    </details>
  </>;
}
