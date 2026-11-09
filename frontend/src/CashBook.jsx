import { businessDate, businessFinancialYear } from "./businessDate.js";
import React, {useEffect, useState} from 'react';
import {downloadBlob} from './downloadBlob.js';

const rupees = value => new Intl.NumberFormat('en-IN', {style: 'currency', currency: 'INR'}).format(Number(value || 0));
const today = () => businessDate();

export default function CashBook({companyId, records, bankAccount}) {
  const [from, setFrom] = useState(() => `${businessFinancialYear()}-04-01`);
  const [to, setTo] = useState(today);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const bankId = bankAccount?.id || 'default';
  const query = `from_date=${encodeURIComponent(from)}&to_date=${encodeURIComponent(to)}&bank_account_id=${encodeURIComponent(bankId)}`;
  const requestKey = `${companyId}|${query}`;
  const data = result?.key === requestKey ? result.value : null;
  useEffect(() => {
    if (!companyId || !from || !to) return;
    let active = true;
    setResult(null); setError('');
    fetch(`/api/companies/${companyId}/cash-book?${query}`, {headers: {Authorization: `Bearer ${localStorage.token}`}})
      .then(async response => {const result = await response.json(); if (!response.ok) throw Error(result.detail || 'Could not load cash book'); return result;})
      .then(value => {if (active) setResult({key: requestKey, value});})
      .catch(err => {if (active) setError(err.message);});
    return () => {active = false;};
  }, [companyId, records, bankId, from, to]);
  async function download(format) {
    try {
      const response = await fetch(`/api/companies/${companyId}/cash-book.${format}?${query}`, {headers: {Authorization: `Bearer ${localStorage.token}`}});
      if (!response.ok) throw Error('Could not export cash book');
      downloadBlob(await response.blob(), `apex-cash-book.${format}`);
    } catch (err) {setError(err.message);}
  }
  return <>
    <div className="summary-grid bank-summary"><div className="summary-card"><div className="summary-top">CASH BALANCE</div><strong>{data ? rupees(data.closing.cash) : '—'}</strong><small>Through {to}</small></div><div className="summary-card"><div className="summary-top">{bankAccount?.name || 'Bank clearing'} BALANCE</div><strong>{data ? rupees(data.closing.bank) : '—'}</strong><small>Through {to}</small></div></div>
    {error && <div className="error banner">{error}</div>}
    <section className="panel register cash-book"><div className="panel-header"><div><h2>Cash and bank book</h2><p>Posted ledger movements for cash and the selected bank.</p></div><div className="heading-actions"><button className="button secondary" disabled={!data} onClick={() => download('xlsx')}>XLSX</button><button className="button secondary" disabled={!data} onClick={() => download('pdf')}>PDF</button></div></div>
      <div className="cash-book-filters"><label>From<input type="date" value={from} onChange={event => setFrom(event.target.value)}/></label><label>To<input type="date" value={to} onChange={event => setTo(event.target.value)}/></label>{data && <p>Opening cash {rupees(data.opening.cash)} · bank {rupees(data.opening.bank)}</p>}</div>
      {data && <div className="table-wrap" tabIndex={0}><table><thead><tr><th>DATE</th><th>REFERENCE / DESCRIPTION</th><th>TYPE</th><th className="right">CASH</th><th className="right">BANK</th><th className="right">CASH BALANCE</th><th className="right">BANK BALANCE</th></tr></thead><tbody>{data.rows.map(row => <tr key={row.id}><td>{row.date}</td><td>{row.reference}<small className="bank-ref">{row.description}</small></td><td>{row.kind.replaceAll('_', ' ')}</td><td className="right">{rupees(row.cash)}</td><td className="right">{rupees(row.bank)}</td><td className="right">{rupees(row.cash_balance)}</td><td className="right">{rupees(row.bank_balance)}</td></tr>)}</tbody></table>{!data.rows.length && <div className="empty"><strong>No posted movements in this period</strong></div>}</div>}
    </section><div className="info-box">Manual journals and reversals are included. Movements on the same date use a consistent order.</div>
  </>;
}
