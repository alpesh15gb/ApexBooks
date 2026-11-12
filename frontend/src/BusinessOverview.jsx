import { businessDate, businessDashboardRange } from "./businessDate.js";
import { dashboardWork, recentTransactions } from "./dashboardModel.js";
import SetupChecklist from "./SetupChecklist.jsx";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Banknote,
  BarChart3,
  CalendarDays,
  ChevronRight,
  Clock3,
  FileText,
  Landmark,
  Plus,
  RefreshCw,
  ShoppingBag,
  TrendingUp,
  Wallet,
} from "lucide-react";

const money = (value) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
const compact = (value) =>
  new Intl.NumberFormat("en-IN", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
const dateText = (value) =>
  new Date(value + "T00:00:00").toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
const iso = (date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
function rangeFor(period) { return businessDashboardRange(period); }

function Metric({ label, value, note, icon: Icon, tone = "green" }) {
  const display = value == null ? "—" : money(value);
  return (
    <article className={`overview-metric metric-${tone}`} data-wide-amount={display.length > 14} style={{ '--amount-scale': `${Math.min(14, 150 / display.length)}cqi` }}>
      <div>
        <span>{label}</span>
        <Icon size={18} />
      </div>
      <strong>{display}</strong>
      <small>{note}</small>
    </article>
  );
}

function SalesChart({ records, start, end }) {
  const chartRef = useRef(null),
    [chartWidth, setChartWidth] = useState(640);
  useEffect(() => {
    const node = chartRef.current;
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width) setChartWidth(Math.max(300, width));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const series = useMemo(() => {
    const buckets = [];
    const cursor = new Date(start + "T00:00:00");
    cursor.setDate(1);
    while (iso(cursor) <= end && buckets.length < 13) {
      buckets.push({
        key: iso(cursor).slice(0, 7),
        label: cursor.toLocaleDateString("en-IN", { month: "short" }),
        sales: 0,
        purchases: 0,
      });
      cursor.setMonth(cursor.getMonth() + 1);
    }
    for (const r of records) {
      if (!r.posted || r.cancelled || r.data?.cancelled || r.date < start || r.date > end) continue;
      const row = buckets.find((x) => x.key === r.date.slice(0, 7));
      if (!row) continue;
      const n = Number(r.amount || 0);
      if (["sales_invoice", "pos"].includes(r.kind)) row.sales += n;
      else if (r.kind === "credit_note") row.sales -= n;
      else if (r.kind === "purchase_bill") row.purchases += n;
      else if (r.kind === "debit_note") row.purchases -= n;
    }
    return buckets;
  }, [records, start, end]);
  const values = series.flatMap((x) => [x.sales, x.purchases]),
    max = Math.max(0, ...values),
    min = Math.min(0, ...values),
    span = max - min || 1;
  const y = (n) => 159 - ((n - min) / span) * 128,
    base = y(0),
    space = (chartWidth - 66) / Math.max(series.length, 1),
    bw = Math.min(21, space * 0.27);
  return (
    <>
      <div className="insight-legend">
        <span>
          <i className="legend-sales" />
          Net sales
        </span>
        <span>
          <i className="legend-purchases" />
          Net purchases
        </span>
        <small>Invoice values, including GST where applicable</small>
      </div>
      <div className="chart-container" ref={chartRef}>
        {max === 0 && min === 0 ? (
          <div className="chart-empty">
            <BarChart3 size={32} />
            <strong>No net movement in this period</strong>
            <p>Posted sales and purchases will appear here.</p>
          </div>
        ) : (
          <div className="overview-chart">
            <svg
              viewBox={`0 0 ${chartWidth} 200`}
              role="img"
              aria-label="Monthly net sales and purchases from posted documents"
            >
              <title>
                Net sales and purchases, {dateText(start)} to {dateText(end)}
              </title>
              {[max, (max + min) / 2, min].map((n, i) => (
                <g key={i}>
                  <line
                    x1="50"
                    x2={chartWidth - 10}
                    y1={y(n)}
                    y2={y(n)}
                    stroke="#e7eaf0"
                    strokeDasharray="4 5"
                  />
                  <text
                    x="39"
                    y={y(n) + 4}
                    textAnchor="end"
                    fill="#778591"
                    fontSize="11"
                  >
                    {compact(n)}
                  </text>
                </g>
              ))}
              <line
                x1="50"
                x2={chartWidth - 10}
                y1={base}
                y2={base}
                stroke="#bac1cd"
              />
              {series.map((row, index) => (
                <g key={row.key}>
                  <title>
                    {row.label}: sales {money(row.sales)}, purchases{" "}
                    {money(row.purchases)}
                  </title>
                  <rect
                    x={53 + index * space + space / 2 - bw - 3}
                    y={Math.min(base, y(row.sales))}
                    width={bw}
                    height={Math.abs(base - y(row.sales))}
                    rx="4"
                    className="chart-sales-bar"
                    fill="var(--ln-navy-700)"
                  />
                  <rect
                    x={53 + index * space + space / 2 + 3}
                    y={Math.min(base, y(row.purchases))}
                    width={bw}
                    height={Math.abs(base - y(row.purchases))}
                    rx="4"
                    className="chart-purchases-bar"
                    fill="var(--ln-brass)"
                  />
                  <text
                    x={53 + index * space + space / 2}
                    y="186"
                    textAnchor="middle"
                    fill="#71818c"
                    fontSize="12"
                  >
                    {row.label}
                  </text>
                </g>
              ))}
            </svg>
          </div>
        )}
      </div>
      <details className="chart-data">
        <summary>View chart data</summary>
        <div className="table-wrap" tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th>Month</th>
                <th>Net sales</th>
                <th>Net purchases</th>
              </tr>
            </thead>
            <tbody>
              {series.map((row) => (
                <tr key={row.key}>
                  <td>{row.label}</td>
                  <td>{money(row.sales)}</td>
                  <td>{money(row.purchases)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </>
  );
}

export default function BusinessOverview({ company, records, api, onNavigate, onCreate, onOpenRecord, refreshKey = 0, recordsReady = true }) {
  const [period, setPeriod] = useState("year"), [result, setResult] = useState(null), [error, setError] = useState(""), [retry, setRetry] = useState(0);
  const { start, end } = rangeFor(period), key = `${company?.id}|${start}|${end}`;
  useEffect(() => {
    if (!company?.id) return;
    let live = true;
    setError(""); setResult(null);
    Promise.all([
      api(`/companies/${company.id}/reports/summary?from_date=${start}&to_date=${end}`),
      api(`/companies/${company.id}/reports/financial?from_date=${start}&to_date=${end}`),
      api(`/companies/${company.id}/bank-accounts`),
    ]).then(([summary, financial, banks]) => { if (live) setResult({ key, summary, financial, banks }); })
      .catch(e => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [company?.id, start, end, refreshKey, retry]);
  const data = result?.key === key ? result : null;
  const canWrite = ["owner", "editor"].includes(company?.role);
  const { overdue, openBills, quotes } = dashboardWork(records, businessDate());
  const bankCodes = new Set(data?.banks.map(bank => bank.ledger_code) || []);
  const cashAccounts = data?.financial.accounts.filter(a => a.code === "SYS-CASH" || a.code === "SYS-BANK" || bankCodes.has(a.code)) || [];
  const cashTotal = cashAccounts.reduce((sum, a) => sum + Number(a.closing_balance || 0), 0);
  const activity = recentTransactions(records);
  const openRecord = record => onOpenRecord ? onOpenRecord(record) : onNavigate(record.kind, record.number || record.name);
  const txName = { sales_invoice: "Sales invoice", purchase_bill: "Purchase bill", payment_in: "Payment received", payment_out: "Payment made", expense: "Expense", estimate: "Estimate", sales_order: "Sales order", proforma: "Proforma invoice", credit_note: "Credit note", debit_note: "Debit note", pos: "POS sale", purchase_order: "Purchase order", bank_transfer: "Bank transfer" };
  return <div className="business-overview">
    <div className="overview-heading">
      <div><div className="workspace-kicker">OVERVIEW</div><h1>Business overview</h1><p>{company?.name || "Your business"}<span className="overview-subtitle-divider"> / </span>Your financial picture at a glance.</p></div>
      <div className="overview-heading-actions">
        <label className="period-picker"><CalendarDays size={16} /><select aria-label="Dashboard period" value={period} onChange={e => setPeriod(e.target.value)}><option value="year">This financial year</option><option value="month">This month</option><option value="30days">Last 30 days</option></select></label>
        <button className="button primary" disabled={!canWrite || !recordsReady} onClick={() => onCreate("sales_invoice")}><Plus size={17} />New invoice</button>
      </div>
    </div>
    {error && <div className="error banner" role="alert"><span>We couldn't load your overview. {error}</span><button className="text-button" onClick={() => setRetry(x => x + 1)}><RefreshCw size={14} />Retry</button></div>}
    <div className="overview-period-note">{dateText(start)} – {dateText(end)}<span>All amounts in INR</span></div>
    <div className="overview-metrics" aria-busy={!data && !error}>
      <Metric label="Net sales" value={data?.summary.sales} note={company?.tax_mode === "regular" ? "Including GST, after credit notes" : "Sales after credit notes"} icon={TrendingUp} />
      <Metric label="Net profit" value={data?.financial.net_profit} note="Income less costs and expenses" icon={BarChart3} tone="blue" />
      <Metric label="To collect" value={data?.summary.receivables} note={`Outstanding as of ${dateText(end)}`} icon={ArrowDownLeft} tone="purple" />
      <Metric label="To pay" value={data?.summary.payables} note={`Outstanding as of ${dateText(end)}`} icon={Wallet} tone="amber" />
    </div>
    <div className="overview-analytics">
      <section className="insight-card sales-insight"><div className="insight-heading"><div><h2>Sales & purchases</h2><p>Your trading activity for the selected period.</p></div><span className="subtle-tag">Net of returns</span></div>{recordsReady ? <SalesChart records={records} start={start} end={end} /> : <p className="chart-empty" role="status">Loading transactions…</p>}</section>
      <section className="insight-card bank-insight"><div className="insight-heading"><div><h2>Cash & bank</h2><p>Book balance · {dateText(end)}</p></div><Landmark size={20} /></div><strong className="insight-total">{data ? money(cashTotal) : "—"}</strong><div className="money-movement"><div><span><ArrowDownLeft size={14} /> Money in</span><strong>{data ? money(data.summary.receipts) : "—"}</strong></div><div><span><ArrowUpRight size={14} /> Money out</span><strong>{data ? money(data.summary.payments) : "—"}</strong></div><small>For the selected period · excludes account transfers</small></div><div className="bank-mini-list">
        {cashAccounts.length ? cashAccounts.slice(0, 3).map(a => <div key={a.code}><span className="bank-mini-icon">{a.code === "SYS-CASH" ? <Banknote size={17} /> : <Landmark size={17} />}</span><span>{a.name}</span><strong>{money(a.closing_balance)}</strong></div>) : <p>{data ? "Add an account to start tracking your money." : error ? "Balances are unavailable. Please retry." : "Loading balances…"}</p>}
      </div><button className="insight-link" onClick={() => onNavigate("bank_account")}>View accounts & reconcile <ArrowUpRight size={15} /></button></section>
    </div>
    <div className="overview-work-grid">
      <section className="insight-card next-actions" aria-label="Quick actions"><div className="insight-heading"><div><h2>Everyday tasks</h2><p>Start with what you need to do.</p></div></div><div className="task-grid">
        {[["payment_in", "Record a receipt", "Customer payment", ArrowDownLeft], ["purchase_bill", "Add a purchase", "Supplier bill", ShoppingBag], ["expense", "Record an expense", "Business spending", Wallet], ["payment_out", "Pay a supplier", "Bill payment", ArrowUpRight]].map(([kind, title, note, Icon]) => <button key={kind} disabled={!canWrite || !recordsReady} onClick={() => onCreate(kind)}><span className="task-icon"><Icon size={20} /></span><span><strong>{title}</strong><small>{note}</small></span><ChevronRight size={16} /></button>)}
      </div></section>
      <section className="insight-card work-queue"><div className="insight-heading"><div><h2>Needs attention</h2><p>Open work across all dates.</p></div><Clock3 size={19} /></div>
        {[[overdue.length, "Overdue invoices", "sales_invoice", "overdue"], [openBills.length, "Unpaid bills", "purchase_bill", "unpaid"], [quotes.length, "Open estimates", "estimate", "draft"]].map(([count, label, kind, filter]) => <button key={kind} disabled={!recordsReady} onClick={() => onNavigate(kind, "", filter, true)}><span className={count ? "queue-count pending" : "queue-count"}>{recordsReady ? count : "—"}</span><span>{label}</span><ChevronRight size={16} /></button>)}
      </section>
    </div>
    <section className="insight-card activity-insight"><div className="insight-heading"><div><h2>Recent transactions</h2><p>Your latest business activity, in one place.</p></div><button className="insight-link" onClick={() => onNavigate("day_book")}>View day book <ArrowUpRight size={15} /></button></div>
      <div className="table-wrap" tabIndex={0}><table className="recent-table"><thead><tr><th>Transaction</th><th>Reference</th><th>Date</th><th>Status</th><th className="right">Amount</th><th aria-label="Open" /></tr></thead><tbody>
        {activity.map(r => <tr key={r.id} onClick={() => openRecord(r)}><td><div className="recent-name"><span className={`recent-icon ${["purchase_bill", "payment_out", "expense"].includes(r.kind) ? "is-purchase" : ""}`}><FileText size={17} /></span><span><strong>{r.name || "Untitled"}</strong><small>{txName[r.kind] || r.kind.replaceAll("_", " ")}</small></span></div></td><td>{r.number || "—"}</td><td>{dateText(r.date)}</td><td><span className={`status-badge ${r.cancelled ? "cancelled" : r.converted_to ? "converted" : r.posted ? "posted" : "draft"}`}>{r.cancelled ? "Cancelled" : r.converted_to ? "Converted" : r.posted ? "Posted" : ["estimate", "sales_order", "proforma", "purchase_order"].includes(r.kind) ? "Draft" : "Unposted"}</span></td><td className="right">{money(r.amount)}</td><td><button className="round-action" aria-label={`Open ${r.number || r.name}`} onClick={e => { e.stopPropagation(); openRecord(r); }}><ChevronRight size={16} /></button></td></tr>)}
      </tbody></table>{!activity.length && <div className="chart-empty"><FileText size={28} /><strong>{recordsReady ? "Your books start here" : "Loading transactions…"}</strong><p>{recordsReady ? "Create your first invoice or add a purchase bill." : "Your latest activity will appear here."}</p></div>}</div>
    </section>
    {recordsReady && <SetupChecklist company={company} records={records} onCreate={onCreate} onNavigate={onNavigate} api={api} />}
  </div>;
}
