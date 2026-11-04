import { businessDashboardRange } from "./businessDate.js";
import { supportsFeature } from "./capabilities.js";
import SetupChecklist from "./SetupChecklist.jsx";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Banknote,
  BarChart3,
  CalendarDays,
  ChevronRight,
  CircleCheck,
  Clock3,
  FileText,
  Landmark,
  Plus,
  ReceiptIndianRupee,
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
  return (
    <article className={`overview-metric metric-${tone}`}>
      <div>
        <span>{label}</span>
        <Icon size={18} />
      </div>
      <strong>{value == null ? "—" : money(value)}</strong>
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
      if (!r.posted || r.date < start || r.date > end) continue;
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
                    fill="#1f427d"
                  />
                  <rect
                    x={53 + index * space + space / 2 + 3}
                    y={Math.min(base, y(row.purchases))}
                    width={bw}
                    height={Math.abs(base - y(row.purchases))}
                    rx="4"
                    fill="#a8b8d4"
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
        <div className="table-wrap">
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

export default function BusinessOverview({
  features = [],
  company,
  records,
  api,
  onNavigate,
  onCreate,
  refreshKey = 0,
  recordsReady = true,
}) {
  const [period, setPeriod] = useState("year"),
    [result, setResult] = useState(null),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0);
  const { start, end } = rangeFor(period),
    key = `${company?.id}|${start}|${end}`;
  useEffect(() => {
    if (!company?.id) return;
    let live = true;
    setError("");
    setResult(null);
    Promise.all([
      api(
        `/companies/${company.id}/reports/summary?from_date=${start}&to_date=${end}`,
      ),
      api(
        `/companies/${company.id}/reports/financial?from_date=${start}&to_date=${end}`,
      ),
      api(
        `/companies/${company.id}/reports/gst-payable?from_date=2000-01-01&to_date=${end}`,
      ),
      api(`/companies/${company.id}/bank-accounts`),
    ])
      .then(([summary, financial, gst, banks]) => {
        if (live) setResult({ key, summary, financial, gst, banks });
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [company?.id, start, end, refreshKey, retry]);
  const data = result?.key === key ? result : null,
    canWrite = ["owner", "editor"].includes(company?.role);
  const invoices = records.filter(
      (r) => r.kind === "sales_invoice" && r.posted,
    ),
    bills = records.filter((r) => r.kind === "purchase_bill" && r.posted);
  const overdue = invoices.filter(
      (r) =>
        Number(r.outstanding) > 0 && r.data?.due_date && r.data.due_date < end,
    ),
    openBills = bills.filter((r) => Number(r.outstanding) > 0),
    quotes = records.filter((r) => r.kind === "estimate" && !r.converted_to);
  const issued = invoices.reduce((s, r) => s + Number(r.amount || 0), 0),
    outstanding = invoices.reduce((s, r) => s + Number(r.outstanding || 0), 0),
    settled = Math.max(0, issued - outstanding),
    ratio = issued ? Math.min(100, (settled / issued) * 100) : 0;
  const bankCodes = new Set(data?.banks.map((bank) => bank.ledger_code) || []);
  const cashAccounts =
      data?.financial.accounts.filter(
        (a) =>
          a.code === "SYS-CASH" || a.code === "SYS-BANK" || bankCodes.has(a.code),
      ) || [],
    cashTotal = cashAccounts.reduce(
      (sum, a) => sum + Number(a.closing_balance || 0),
      0,
    );
  const activity = records
    .filter((r) => !["party", "item", "bank_account"].includes(r.kind))
    .slice(0, 6);
  const txName = {
    sales_invoice: "Sales invoice",
    purchase_bill: "Purchase bill",
    payment_in: "Payment in",
    payment_out: "Payment out",
    expense: "Expense",
    estimate: "Estimate",
    proforma: "Proforma invoice",
    credit_note: "Credit note",
    debit_note: "Debit note",
    pos: "POS sale",
    purchase_order: "Purchase order",
    bank_transfer: "Bank transfer",
  };
  return (
    <div className="business-overview">
      <div className="overview-heading">
        <div>
          <div className="workspace-kicker">
            <span /> YOUR BUSINESS, IN FOCUS
          </div>
          <h1>Business overview</h1>
          <p>
            {company?.name || "Your company"} <span>·</span> {dateText(start)} –{" "}
            {dateText(end)}
          </p>
        </div>
        <div className="overview-heading-actions">
          <label className="period-picker">
            <CalendarDays size={16} />
            <select
              aria-label="Dashboard period"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            >
              <option value="year">This financial year</option>
              <option value="month">This month</option>
              <option value="30days">Last 30 days</option>
            </select>
          </label>
          <button
            className="button primary"
            disabled={!canWrite}
            onClick={() => onCreate("sales_invoice")}
          >
            <Plus size={17} />
            New invoice
          </button>
        </div>
      </div>
      {recordsReady && <SetupChecklist company={company} records={records} onCreate={onCreate} onNavigate={onNavigate} api={api} />}
      <nav className="overview-tabs" aria-label="Business shortcuts">
        <span className="selected">Overview</span>
        <button onClick={() => onNavigate("sales_invoice")}>
          Sales & collections <ArrowUpRight size={14} />
        </button>
        <button onClick={() => onNavigate("purchase_bill")}>
          Purchases <ArrowUpRight size={14} />
        </button>
        <button disabled={!supportsFeature(features,"recurring_drafts")} title={!supportsFeature(features,"recurring_drafts") ? "Connected API upgrade required" : undefined} onClick={() => onNavigate("recurring")}>Recurring drafts <ArrowUpRight size={14} /></button>
        <button disabled={!supportsFeature(features,"low_stock_reorder")} title={!supportsFeature(features,"low_stock_reorder") ? "Connected API upgrade required" : undefined} onClick={() => onNavigate("reorder")}>Low stock <ArrowUpRight size={14} /></button>
        <button onClick={() => onNavigate("reports")}>
          Reports & GST <ArrowUpRight size={14} />
        </button>
        <span className="books-status">
          <CircleCheck size={14} /> {data && recordsReady ? "Books loaded" : error ? "Unable to load books" : "Loading books"}
        </span>
      </nav>
      {error && (
        <div className="error banner">
          {error}
          <button
            className="text-button"
            onClick={() => setRetry((x) => x + 1)}
          >
            <RefreshCw size={14} />
            Retry
          </button>
        </div>
      )}
      <div className="overview-metrics">
        <Metric
          label="Net sales"
          value={data?.summary.sales}
          note={company?.tax_mode === "regular" ? "Invoice totals incl. GST, after credit notes" : "Posted sales, after credit notes"}
          icon={TrendingUp}
        />
        <Metric
          label="Net profit"
          value={data?.financial.net_profit}
          note="Income less recorded costs & expenses"
          icon={BarChart3}
          tone="blue"
        />
        <Metric
          label="To collect"
          value={data?.summary.receivables}
          note={`Outstanding as of ${dateText(end)}`}
          icon={ArrowDownLeft}
          tone="purple"
        />
        <Metric
          label="To pay"
          value={data?.summary.payables}
          note={`Supplier balances as of ${dateText(end)}`}
          icon={Wallet}
          tone="amber"
        />
      </div>
      <div className="attention-strip">
        <span className="attention-title">
          <Clock3 size={16} />
          Needs attention
        </span>
        <button onClick={() => onNavigate("sales_invoice", "", "overdue")}>
          <strong>{recordsReady ? overdue.length : "—"}</strong> overdue invoices{" "}
          <ChevronRight size={14} />
        </button>
        <button onClick={() => onNavigate("purchase_bill", "", "unpaid")}>
          <strong>{openBills.length}</strong> unpaid bills{" "}
          <ChevronRight size={14} />
        </button>
        <button onClick={() => onNavigate("estimate", "", "draft")}>
          <strong>{quotes.length}</strong> open estimates{" "}
          <ChevronRight size={14} />
        </button>
      </div>
      <div className="overview-analytics">
        <section className="insight-card sales-insight">
          <div className="insight-heading">
            <div>
              <span className="card-kicker">BUSINESS PERFORMANCE</span>
              <h2>Sales & purchases</h2>
            </div>
            <span className="subtle-tag">
              {period === "year"
                ? "Financial year"
                : period === "month"
                  ? "This month"
                  : "Last 30 days"}
            </span>
          </div>
          <SalesChart records={records} start={start} end={end} />
        </section>
        <section className="insight-card collection-insight">
          <div className="insight-heading">
            <div>
              <span className="card-kicker">GET PAID</span>
              <h2>Invoice collections</h2>
            </div>
            <button
              className="round-action"
              aria-label="Open sales invoices"
              onClick={() => onNavigate("sales_invoice")}
            >
              <ArrowUpRight size={17} />
            </button>
          </div>
          <div className="collection-content">
            <div
              className="collection-ring"
              style={{ "--collection-ratio": `${ratio}%` }}
            >
              <div>
                <strong>{Math.round(ratio)}%</strong>
                <small>settled</small>
              </div>
            </div>
            <div className="collection-numbers">
              <div>
                <i className="legend-sales" />
                <span>
                  Settled<strong>{money(settled)}</strong>
                </span>
              </div>
              <div>
                <i className="legend-purchases" />
                <span>
                  Outstanding<strong>{recordsReady ? money(outstanding) : "—"}</strong>
                </span>
              </div>
            </div>
          </div>
          <div className="insight-footnote">
            All posted invoices · settlements include payments, advances and
            credits.
          </div>
        </section>
      </div>
      <div className="overview-secondary">
        <section className="insight-card profit-insight">
          <div className="insight-heading">
            <div>
              <span className="card-kicker">PROFIT & LOSS</span>
              <h2>Your earnings, clearly</h2>
            </div>
            <span className="insight-icon blue">
              <BarChart3 size={19} />
            </span>
          </div>
          <strong className="insight-total">
            {data ? money(data.financial.net_profit) : "—"}
          </strong>
          <span className="insight-caption">Net profit for this period</span>
          {[
            ["Income", data?.financial.income, "income"],
            ["Costs & expenses", data?.financial.expenses, "expense"],
          ].map(([label, value, type]) => (
            <div className={`profit-line ${type}`} key={type}>
              <div>
                <span>{label}</span>
                <strong>{data ? money(value) : "—"}</strong>
              </div>
              <div className="profit-track">
                <span
                  style={{
                    width: `${Math.min(100, (Math.max(0, Number(value || 0)) / Math.max(1, Number(data?.financial.income || 0), Number(data?.financial.expenses || 0))) * 100)}%`,
                  }}
                />
              </div>
            </div>
          ))}
          <button
            className="insight-link"
            onClick={() => onNavigate("reports")}
          >
            Explore your reports <ArrowUpRight size={15} />
          </button>
        </section>
        <section className="insight-card bank-insight">
          <div className="insight-heading">
            <div>
              <span className="card-kicker">CASH & BANK</span>
              <h2>Money at hand</h2>
            </div>
            <span className="insight-icon green">
              <Landmark size={19} />
            </span>
          </div>
          <strong className="insight-total">
            {data ? money(cashTotal) : "—"}
          </strong>
          <span className="insight-caption">
            Book balance as of {dateText(end)}
          </span>
          <div className="bank-mini-list">
            {cashAccounts.length ? (
              cashAccounts.slice(0, 3).map((a) => (
                <div key={a.code}>
                  <span className="bank-mini-icon">
                    {a.code === "SYS-CASH" ? (
                      <Banknote size={17} />
                    ) : (
                      <Landmark size={17} />
                    )}
                  </span>
                  <span>{a.name}</span>
                  <strong>{money(a.closing_balance)}</strong>
                </div>
              ))
            ) : (
              <p>
                {data
                  ? "No cash or bank movement recorded yet."
                  : error ? "Account balances are temporarily unavailable. Use Retry above." : "Loading account balances…"}
              </p>
            )}
          </div>
          <button
            className="insight-link"
            onClick={() => onNavigate("bank_account")}
          >
            Manage & reconcile accounts <ArrowUpRight size={15} />
          </button>
        </section>
        <section className="insight-card gst-insight">
          <div className="insight-heading">
            <div>
              <span className="card-kicker">
                {company?.tax_mode === "regular"
                  ? "GST POSITION · TO DATE"
                  : "YOUR TAX PROFILE"}
              </span>
              <h2>
                {company?.tax_mode === "regular"
                  ? "GST payable"
                  : company?.tax_mode === "composition"
                    ? "Composition business"
                    : "Non-GST business"}
              </h2>
            </div>
            <span className="insight-icon amber">
              <ReceiptIndianRupee size={19} />
            </span>
          </div>
          {company?.tax_mode === "regular" ? (
            <>
              <strong className="insight-total">
                {data ? money(data.gst.cash_total) : "—"}
              </strong>
              <span className="insight-caption">
                Estimated after permitted input set-off
              </span>
              <div className="gst-mini-line">
                <span>Output GST</span>
                <strong>
                  {data ? money(
                    Object.values(data?.gst.output || {}).reduce(
                      (a, b) => a + Number(b),
                      0,
                    ),
                  ) : "—"}
                </strong>
              </div>
              <div className="gst-mini-line">
                <span>Input from supplier bills</span>
                <strong>
                  {data ? money(
                    Object.values(data?.gst.book_itc || {}).reduce(
                      (a, b) => a + Number(b),
                      0,
                    ),
                  ) : "—"}
                </strong>
              </div>
              <p className="gst-disclaimer">
                Book estimate. Verify ITC eligibility and GSTR-2B before filing.
              </p>
            </>
          ) : (
            <>
              <p className="non-gst-profile">
                {company?.tax_mode === "composition"
                  ? "Create bills of supply and track supplier GST within your purchase costs."
                  : "Invoice, track stock and manage your business without collecting GST."}
              </p>
              <span className="profile-badge">
                <CircleCheck size={14} />{" "}
                {company?.tax_mode === "composition"
                  ? "Composition profile"
                  : "Works without GST registration"}
              </span>
            </>
          )}
          <button
            className="insight-link"
            onClick={() => onNavigate("reports")}
          >
            View tax & purchase reports <ArrowUpRight size={15} />
          </button>
        </section>
      </div>
      <div className="overview-bottom">
        <section className="insight-card activity-insight">
          <div className="insight-heading">
            <div>
              <span className="card-kicker">YOUR BOOKS</span>
              <h2>Recent transactions</h2>
            </div>
            <button
              className="insight-link"
              onClick={() => onNavigate("reports")}
            >
              View reports <ArrowUpRight size={15} />
            </button>
          </div>
          <div className="table-wrap">
            <table className="recent-table">
              <thead>
                <tr>
                  <th>Transaction</th>
                  <th>Reference</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th className="right">Amount</th>
                  <th aria-label="Open" />
                </tr>
              </thead>
              <tbody>
                {activity.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => onNavigate(r.kind, r.number || r.name)}
                  >
                    <td>
                      <div className="recent-name">
                        <span
                          className={`recent-icon ${["purchase_bill", "payment_out", "expense"].includes(r.kind) ? "is-purchase" : ""}`}
                        >
                          {["purchase_bill", "expense"].includes(r.kind) ? (
                            <ShoppingBag size={17} />
                          ) : (
                            <FileText size={17} />
                          )}
                        </span>
                        <span>
                          <strong>{r.name || "Untitled"}</strong>
                          <small>
                            {txName[r.kind] || r.kind.replaceAll("_", " ")}
                          </small>
                        </span>
                      </div>
                    </td>
                    <td>{r.number || "—"}</td>
                    <td>{dateText(r.date)}</td>
                    <td>
                      <span
                        className={`status-badge ${r.cancelled ? "cancelled" : r.converted_to ? "converted" : r.posted ? "posted" : "draft"}`}
                      >
                        {r.cancelled ? "Cancelled" : r.converted_to
                          ? "Converted"
                          : r.posted
                            ? "Posted"
                            : [
                                  "estimate",
                                  "proforma",
                                  "purchase_order",
                                ].includes(r.kind)
                              ? "Draft"
                              : "Unposted"}
                      </span>
                    </td>
                    <td className="right">{money(r.amount)}</td>
                    <td>
                      <button
                        className="round-action"
                        aria-label={`Open ${r.number || r.name}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onNavigate(r.kind, r.number || r.name);
                        }}
                      >
                        <ChevronRight size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!activity.length && (
              <div className="chart-empty">
                <FileText size={30} />
                <strong>Your books start here</strong>
                <p>Create your first invoice or add a purchase bill.</p>
              </div>
            )}
          </div>
        </section>
        <section className="insight-card action-insight">
          <span className="card-kicker">KEEP BUSINESS MOVING</span>
          <h2>What would you like to do?</h2>
          {[
            [
              "sales_invoice",
              "Create an invoice",
              "Bill your customer",
              FileText,
            ],
            [
              "purchase_bill",
              "Add a purchase",
              "Scan or enter a supplier bill",
              ShoppingBag,
            ],
            [
              "payment_in",
              "Receive a payment",
              "Settle an outstanding invoice",
              ArrowDownLeft,
            ],
            ["party", "Add a party", "Customers & suppliers", Plus],
          ].map(([kind, title, note, Icon]) => (
            <button
              key={kind}
              disabled={!canWrite}
              onClick={() => onCreate(kind)}
            >
              <span className="action-icon">
                <Icon size={18} />
              </span>
              <span>
                <strong>{title}</strong>
                <small>{note}</small>
              </span>
              <ChevronRight size={16} />
            </button>
          ))}
        </section>
      </div>
    </div>
  );
}
