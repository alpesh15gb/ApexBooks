import { businessDate } from "./businessDate.js";
import React, { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

const rupees = (value) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(value || 0));

export function shiftDay(day, by) {
  const [y, m, d] = day.split("-").map(Number);
  const next = new Date(Date.UTC(y, m - 1, d + by));
  return next.toISOString().slice(0, 10);
}

// Day book (Vyapar / MyBillBook style): everything dated one day, with money in and out.
export default function DayBook({ companyId, records, api, labels, onOpen }) {
  const [day, setDay] = useState(businessDate);
  const [result, setResult] = useState(null);
  const [failure, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const key = `${companyId}|${day}`;
  const data = result?.key === key && result.records === records ? result.value : null;
  const error = failure?.key === key ? failure.message : "";
  useEffect(() => {
    if (!companyId || !day) return;
    let active = true;
    setError(null);
    setResult(null);
    api(`/companies/${companyId}/day-book?day=${encodeURIComponent(day)}`)
      .then((value) => active && setResult({ key, value, records }))
      .catch((err) => active && setError({key, message: err.message || "Could not load the day book."}));
    return () => { active = false; };
  }, [companyId, day, records, attempt]);
  const totals = data?.totals;
  const availableRecords = new Set(records.map(record => record.id));
  const open = (row) => {
    const record = records.find((r) => r.id === row.id);
    if (record && onOpen) onOpen(record);
  };
  return (
    <>
      <div className="day-book-bar">
        <button type="button" className="button secondary icon" aria-label="Previous day" onClick={() => setDay(shiftDay(day, -1))}><ChevronLeft size={16} /></button>
        <input type="date" aria-label="Day" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} />
        <button type="button" className="button secondary icon" aria-label="Next day" onClick={() => setDay(shiftDay(day, 1))}><ChevronRight size={16} /></button>
        {day !== businessDate() && <button type="button" className="button secondary" onClick={() => setDay(businessDate())}>Today</button>}
      </div>
      <div className="summary-grid day-book-summary">
        <div className="summary-card"><div className="summary-top">SALES</div><strong>{totals ? rupees(totals.sales) : "—"}</strong></div>
        <div className="summary-card"><div className="summary-top">PURCHASES & EXPENSES</div><strong>{totals ? rupees(Number(totals.purchases) + Number(totals.expenses)) : "—"}</strong></div>
        <div className="summary-card"><div className="summary-top">MONEY IN</div><strong className="positive">{totals ? rupees(totals.money_in) : "—"}</strong></div>
        <div className="summary-card"><div className="summary-top">MONEY OUT</div><strong className="negative">{totals ? rupees(totals.money_out) : "—"}</strong><small>{totals ? `Net ${rupees(totals.net)}` : ""}</small></div>
      </div>
      {error && <div><div className="error banner" role="alert">{error}</div><button type="button" className="button secondary" onClick={() => setAttempt(value => value + 1)}>Retry day book</button></div>}
      <section className="panel register day-book">
        <div className="panel-header"><div><h2>Day book · {day}</h2><p role="status">{data ? `${data.count} ${data.count === 1 ? "entry" : "entries"}` : error ? "Day book unavailable" : "Loading…"} · cash and bank movement from posted entries</p></div></div>
        {data && (
          <div className="table-wrap" tabIndex={0}>
            <table>
              <thead><tr><th>TYPE</th><th>NUMBER / PARTY</th><th className="right">AMOUNT</th><th className="right">MONEY IN</th><th className="right">MONEY OUT</th></tr></thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={row.id} className={row.cancelled ? "muted" : ""}>
                    <td>{labels[row.kind] || row.kind.replaceAll("_", " ")}{row.cancelled ? " · cancelled" : row.status === "converted" ? " · converted" : !row.posted && row.kind !== "journal" ? row.status === "non_posting" ? " · non-posting" : " · unposted" : ""}</td>
                    <td>{row.kind !== "journal" && onOpen && availableRecords.has(row.id) ? <button type="button" className="link" aria-label={`Open ${row.display_number || row.number || row.name || "document"}`} onClick={() => open(row)}>{row.display_number || row.number || row.name || "Open document"}</button> : row.display_number || row.number || "—"}{row.display_number && row.display_number !== row.number && <details><summary>Technical reference</summary>{row.number}</details>}<small className="bank-ref">{row.name}</small></td>
                    <td className="right">{rupees(row.amount)}{row.kind === "journal" && row.debit_total != null && <small className="bank-ref">Debit {rupees(row.debit_total)} · Credit {rupees(row.credit_total)}</small>}</td>
                    <td className="right positive">{Number(row.money_in) ? rupees(row.money_in) : ""}</td>
                    <td className="right negative">{Number(row.money_out) ? rupees(row.money_out) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.rows.length && <div className="empty"><strong>Nothing recorded on this day</strong></div>}
          </div>
        )}
      </section>
    </>
  );
}
