import {sessionFetch as fetch, captureSession} from './sessionScope.js';
import {createRequestScope} from './requestScope.js';
import FinancialFigure from "./FinancialFigure.jsx";
import { businessDate, businessFinancialYear } from "./businessDate.js";
import ReportLibrary, { reportInfo, reportGroups } from "./ReportLibrary.jsx";
import DateRangeFilter from "./DateRangeFilter.jsx";
import GstReturnView from "./GstReturnView.jsx";
import StatementsView from "./StatementsView.jsx";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Download, ArrowLeft } from "lucide-react";
import { downloadBlob } from "./downloadBlob.js";

const rupees = (value) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(
    Number(value || 0),
  );
const today = () => businessDate();
const gstViews = ["gstr1", "gstr2a", "gstr3b"];
function returnDates(month, quarterly = false) {
  const [year, selectedMonth] = month.split("-").map(Number);
  const start = quarterly
    ? Math.floor((selectedMonth - 1) / 3) * 3
    : selectedMonth - 1;
  const from = `${year}-${String(start + 1).padStart(2, "0")}-01`;
  const end = new Date(Date.UTC(year, start + (quarterly ? 3 : 1), 0));
  return [
    from,
    `${year}-${String(end.getUTCMonth() + 1).padStart(2, "0")}-${String(end.getUTCDate()).padStart(2, "0")}`,
  ];
}
const api = async (path) => {
  const response = await fetch(`/api${path}`, {
    headers: { Authorization: `Bearer ${localStorage.token}` },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json();
};

export default function Reports({ companyId, records }) {
  const financialYear = businessFinancialYear();
  const [from, setFrom] = useState(`${financialYear}-04-01`);
  const [to, setTo] = useState(today());
  const [view, setView] = useState("summary");
  const [library, setLibrary] = useState(true);
  const [period, setPeriod] = useState("year");
  const [partySelection, setPartySelection] = useState({ companyId, name: "" });
  const selectedParty = partySelection.companyId === companyId ? partySelection.name : "";
  const setParty = (name) => setPartySelection({ companyId, name });
  const [ordinaryDates, setOrdinaryDates] = useState(null);
  const [quarterly, setQuarterly] = useState(false);
  const isGst = gstViews.includes(view);
  function chooseReport(key) {
    setView(key);
    if (gstViews.includes(key) && !gstViews.includes(view)) {
      setOrdinaryDates({ from, to, period });
      const dates = returnDates(today().slice(0, 7));
      setFrom(dates[0]);
      setTo(dates[1]);
      setQuarterly(false);
    } else if (!gstViews.includes(key) && gstViews.includes(view) && ordinaryDates) {
      setFrom(ordinaryDates.from);setTo(ordinaryDates.to);setPeriod(ordinaryDates.period);
    }
  }
  function updateReturnMonth(value) {
    if (!/^\d{4}-\d{2}$/.test(value)) return;
    const dates = returnDates(value, quarterly);
    setFrom(dates[0]);
    setTo(dates[1]);
  }
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [view, library]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const parties = useMemo(
    () =>
      [
        ...new Set(
          records
            .filter(
              (r) =>
                r.kind === "party" ||
                (["sales_invoice", "purchase_bill"].includes(r.kind) &&
                  r.posted),
            )
            .map((r) => r.name),
        ),
      ].sort(),
    [records],
  );
  const party = parties.includes(selectedParty) ? selectedParty : "";
  const endpoint = ["sales", "purchases", "expenses"].includes(view)
    ? "register"
    : view;
  const query = ["ageing", "credits", "advances"].includes(view)
    ? `as_of=${encodeURIComponent(to)}&party=${encodeURIComponent(party)}`
    : `from_date=${encodeURIComponent(from)}&to_date=${encodeURIComponent(to)}${view === "parties" ? `&party=${encodeURIComponent(party)}` : ""}${endpoint === "register" ? `&group=${view}` : ""}`;
  const requestKey = `${companyId}|${view}|${query}`;
  const asOf = ["ageing", "credits", "advances"].includes(view);
  const invalidRange = !to || (!asOf && (!from || from > to));
  const data =
    !invalidRange && result?.key === requestKey ? result.value : null;

  const exportContext = useMemo(() => ({requestKey, library, records}), [requestKey, library, records]);
  const exportScope = useRef(createRequestScope(exportContext));
  exportScope.current.setContext(exportContext);
  useEffect(() => () => exportScope.current.setContext(Symbol('unmounted')), []);

  useEffect(() => {
    if (!companyId || library || invalidRange) return;
    let active = true;
    setResult(null);
    setError("");
    api(
      `/companies/${companyId}/${["gstr1", "gstr2a", "gstr3b"].includes(view) ? "gst-returns" : "reports"}/${endpoint}?${query}`,
    )
      .then((value) => {
        if (active) {
          setResult({ key: requestKey, value });
          setError("");
        }
      })
      .catch((err) => {
        if (active) setError(err.message);
      });
    return () => {
      active = false;
    };
  }, [companyId, view, from, to, party, records, library, invalidRange]);

  async function download(format) {
    if (!data || library) return;
    const current = exportScope.current.capture();
    try {
      const verifySession = captureSession();
      const response = await fetch(
        `/api/companies/${companyId}/${["gstr1", "gstr2a", "gstr3b"].includes(view) ? "gst-returns" : "reports"}/${endpoint}.${format}?${query}`,
        { headers: { Authorization: `Bearer ${localStorage.token}` } },
      );
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw Error(
          typeof body.detail === "string"
            ? body.detail
            : body.detail?.message || "Export failed",
        );
      }
      const filename =
        response.headers
          .get("Content-Disposition")
          ?.match(/filename="([^"]+)"/)?.[1] ||
        `apex-${view}-${from}-${to}.${format}`;
      const blob = await response.blob();
      if (!current()) return;
      verifySession();
      downloadBlob(blob, filename);
    } catch (err) {
      if (current()) setError(err.message);
    }
  }

  if (library)
    return (
      <ReportLibrary
        onSelect={(key) => {
          chooseReport(key);
          setLibrary(false);
        }}
      />
    );
  return (
    <div className={`reports-page ${view}-page`}>
      <div className="page-heading">
        <div>
          <button
            className="link reports-back"
            onClick={() => setLibrary(true)}
          >
            <ArrowLeft size={16} />
            All reports
          </button>
          <h1>{reportInfo[view].title}</h1>
          <p>{reportInfo[view].description}</p>
        </div>
        <div className="heading-actions">
          <button
            className="button secondary"
            onClick={() => download("xlsx")}
            disabled={!data}
          >
            <Download size={16} />{" "}
            {view === "gstr1"
              ? "GSTN format XLSX"
              : view === "gstr2a"
                ? "Purchase books XLSX"
                : view === "gstr3b"
                  ? "3B working XLSX"
                  : "XLSX"}
          </button>
          <button
            className="button secondary"
            onClick={() => download("pdf")}
            disabled={!data}
          >
            <Download size={16} /> {isGst ? "Working PDF" : "PDF"}
          </button>
          {view === "gstr1" && (
            <button
              className="button secondary"
              onClick={() => download("json")}
              disabled={!data?.export_info?.json_available}
              title={
                data?.export_info?.json_available
                  ? "Preparation JSON for review in the GST offline tool"
                  : "Resolve the preparation checks shown below"
              }
            >
              <Download size={16} /> Draft JSON
            </button>
          )}
        </div>
      </div>
      <div className="report-filters panel report-workbench-filters">
        <label>
          Report
          <select
            className="form-select"
            value={view}
            onChange={(e) => chooseReport(e.target.value)}
          >
            {reportGroups.map((group) => (
              <optgroup key={group.title} label={group.title}>
                {group.reports.map(([key, title]) => (
                  <option key={key} value={key}>
                    {title}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        {isGst ? (
          <>
            <label>
              Return frequency
              <select
                className="form-select"
                value={quarterly ? "quarter" : "month"}
                onChange={(e) => {
                  const next = e.target.value === "quarter";
                  setQuarterly(next);
                  const dates = returnDates(from.slice(0, 7), next);
                  setFrom(dates[0]);
                  setTo(dates[1]);
                }}
              >
                <option value="month">Monthly</option>
                <option value="quarter">Quarterly</option>
              </select>
            </label>
            <label>
              {quarterly ? "Month in return quarter" : "Return month"}
              <input
                type="month"
                className="form-select"
                value={from.slice(0, 7)}
                onInput={(e) => updateReturnMonth(e.target.value)}
                onChange={(e) => updateReturnMonth(e.target.value)}
              />
            </label>
            <p className="muted">
              {from} to {to}
            </p>
          </>
        ) : asOf ? (
          <label>
            As of
            <input
              type="date"
              value={to}
              onInput={(e) => setTo(e.target.value)}
              onChange={(e) => setTo(e.target.value)}
            />
          </label>
        ) : (
          <DateRangeFilter
            allowAll={false}
            value={{ period, from, to }}
            onChange={(value) => {
              setPeriod(value.period);
              setFrom(value.from);
              setTo(value.to);
            }}
          />
        )}
        {["parties", "ageing", "credits", "advances"].includes(view) && (
          <label>
            Party
            <select
              className="form-select"
              value={party}
              onChange={(e) => setParty(e.target.value)}
            >
              <option value="">All parties</option>
              {parties.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
        )}
      </div>
      {invalidRange && (
        <div className="error banner" role="alert">
          Choose valid dates. The From date must be on or before the To date.
        </div>
      )}
      {!data && !error && !invalidRange && (
        <div className="report-loading" role="status">
          Loading report…
        </div>
      )}
      {error && <div className="error banner" role="alert">{error}</div>}
      {data && ["gstr1", "gstr2a", "gstr3b"].includes(view) && (
        <GstReturnView data={data} />
      )}
      {data && view === "summary" && "sales" in data && (
        <>
          <div className="summary-grid">
            <Metric label="NET SALES" value={data.sales} />
            <Metric label="NET PURCHASES" value={data.purchases} />
            <Metric label="RECEIVABLES" value={data.receivables} />
            <Metric label="PAYABLES" value={data.payables} />
          </div>
          <div className="report-grid">
            <section className="panel settings-panel">
              <h2>Cash activity</h2>
              <Line label="Payments received" value={data.receipts} />
              <Line label="Payments out" value={data.payments} />
              <Line label="Expenses" value={data.expenses} />
            </section>
            <section className="panel settings-panel">
              <h2>GST summary</h2>
              {data.gst ? (
                <>
                  <p>
                    Input tax is pending review and is not a claimed credit.
                  </p>
                  {["cgst", "sgst", "igst"].map((key) => (
                    <React.Fragment key={key}>
                      <Line
                        label={`${key.toUpperCase()} output`}
                        value={data.gst[key]}
                      />
                      <Line
                        label={`${key.toUpperCase()} input pending`}
                        value={data.gst.input_pending_review[key]}
                      />
                    </React.Fragment>
                  ))}
                  <Line
                    label="Supplier GST included in cost"
                    value={data.gst.input_ineligible_in_cost}
                  />
                  <p className="eyebrow">OUTWARD SUPPLY VALUES</p>
                  {[
                    ["taxable", "Taxable"],
                    ["nil_rated", "Nil rated"],
                    ["exempt", "Exempt"],
                    ["non_gst", "Non-GST"],
                  ].map(([key, label]) => (
                    <Line
                      key={key}
                      label={label}
                      value={data.gst.outward_supply_values?.[key]}
                    />
                  ))}
                </>
              ) : (
                <p>
                  GST return figures are shown only for regular GST companies.
                  Composition and unregistered purchases do not create input
                  credit here.
                </p>
              )}
            </section>
          </div>
          <div className="info-box">
            Receivables and payables are outstanding as of the end date,
            including documents issued before the selected period.{" "}
            {
              records.filter(
                (r) =>
                  r.posted === false &&
                  [
                    "sales_invoice",
                    "purchase_bill",
                    "payment_in",
                    "payment_out",
                  ].includes(r.kind),
              ).length
            }{" "}
            legacy records are excluded. These figures are preparation aids, not
            filed returns.
          </div>
        </>
      )}
      {data && view === "statements" && data.profit_loss && <StatementsView data={data} />}
      {data && view === "financial" && Array.isArray(data.accounts) && (
        <>
          <div className="summary-grid">
            <Metric label="INCOME" value={data.income} />
            <Metric label="EXPENSES" value={data.expenses} />
            <Metric label="NET PROFIT" value={data.net_profit} />
            <Metric label="ASSETS" value={data.assets} />
          </div>
          <div className="report-grid">
            <section className="panel settings-panel">
              <h2>Balance sheet at {to}</h2>
              <Line label="Assets" value={data.assets} />
              <Line label="Liabilities" value={data.liabilities} />
              <Line label="Equity" value={data.equity} />
              <Line label="Retained earnings" value={data.retained_earnings} />
              <Line
                label="Balance difference"
                value={data.balance_difference}
              />
            </section>
            <section className="panel settings-panel">
              <h2>Profit and loss</h2>
              <Line label="Income" value={data.income} />
              <Line
                label="Expenses and cost of goods sold"
                value={data.expenses}
              />
              <Line label="Net profit" value={data.net_profit} />
            </section>
          </div>
          <section className="panel register">
            <div className="panel-header">
              <h2>Account balances</h2>
            </div>
            <div className="table-wrap" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th>ACCOUNT</th>
                    <th>CATEGORY</th>
                    <th className="right">PERIOD</th>
                    <th className="right">CLOSING</th>
                  </tr>
                </thead>
                <tbody>
                  {data.accounts.map((row) => (
                    <tr key={row.code}>
                      <td>
                        {String(row.code).startsWith("BANK-") ? row.name : `${row.code} · ${row.name}`}
                      </td>
                      <td>{row.category}</td>
                      <td className="right">{rupees(row.period_balance)}</td>
                      <td className="right">{rupees(row.closing_balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <div className="info-box">
            Linked tracked purchases are carried as inventory at cost; tracked
            sales post cost of goods sold. Net realisable value write-downs and
            depreciation are not calculated.
          </div>
        </>
      )}
      {data && ["credits", "advances"].includes(view) && (
        <>
          <div className="summary-grid">
            <Metric label="CUSTOMER BALANCE" value={data.totals.customer} />
            <Metric label="SUPPLIER BALANCE" value={data.totals.supplier} />
          </div>
          <section className="panel register">
            <div className="panel-header">
              <h2>
                {view === "credits" ? "Credit" : "Advance"} balances as of{" "}
                {data.as_of}
              </h2>
            </div>
            <div className="table-wrap" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th>DATE</th>
                    <th>REFERENCE / PARTY</th>
                    <th>SIDE</th>
                    <th>ORIGINAL</th>
                    {view === "credits" && <th>ORIGINAL OFFSET</th>}
                    <th>
                      {view === "credits"
                        ? "LATER APPLIED / REFUNDED"
                        : "APPLIED / REFUNDED"}
                    </th>
                    <th>AVAILABLE</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.id}>
                      <td>{row.date}</td>
                      <td>
                        {row.number}
                        <small className="bank-ref">{row.party}</small>
                      </td>
                      <td>{row.side}</td>
                      <td>{rupees(row.issued ?? row.amount)}</td>
                      {view === "credits" && (
                        <td>{rupees(row.original_offset)}</td>
                      )}
                      <td>
                        {rupees(
                          view === "credits"
                            ? Number(row.issued) -
                                Number(row.original_offset) -
                                Number(row.available)
                            : row.applied,
                        )}
                      </td>
                      <td>{rupees(row.available)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!data.rows.length && (
                <div className="empty">
                  <strong>No balances to display</strong>
                </div>
              )}
            </div>
          </section>
        </>
      )}
      {data && view === "parties" && Array.isArray(data.rows) && (
        <>
          <div className="summary-grid">
            <Metric
              label="OPENING RECEIVABLE"
              value={data.opening_receivable}
            />
            <Metric label="OPENING PAYABLE" value={data.opening_payable} />
            <Metric
              label="CLOSING RECEIVABLE"
              value={data.closing_receivable}
            />
            <Metric label="CLOSING PAYABLE" value={data.closing_payable} />
          </div>
          <section className="panel register">
            <div className="panel-header">
              <h2>{party || "All parties"} · Statement</h2>
              {data.ordering_note && <p>{data.ordering_note}</p>}
            </div>
            <div className="table-wrap" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th>DATE</th>
                    <th>PARTY / REFERENCE</th>
                    <th>TYPE</th>
                    <th className="right">AMOUNT</th>
                    <th className="right">RECEIVABLE</th>
                    <th className="right">PAYABLE</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row, index) => (
                    <tr key={index}>
                      <td>{row.date}</td>
                      <td>
                        {row.party}
                        <small className="bank-ref">{row.number}</small>
                      </td>
                      <td>{row.kind.replaceAll("_", " ")}</td>
                      <td className="right">{rupees(row.amount)}</td>
                      <td className="right">{rupees(row.receivable)}</td>
                      <td className="right">{rupees(row.payable)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!data.rows.length && (
                <div className="empty">
                  <strong>No activity in this period</strong>
                </div>
              )}
            </div>
          </section>
          <div className="info-box">
            Party names are matched by text. Posted opening balances and settlements are included;
            activity before the selected start date forms the opening balance.
          </div>
        </>
      )}
      {data && view === "ageing" && Array.isArray(data.rows) && (
        <>
          <div className="summary-grid">
            <Metric label="RECEIVABLE" value={data.totals.receivable} />
            <Metric label="PAYABLE" value={data.totals.payable} />
          </div>
          <section className="panel register">
            <div className="panel-header">
              <h2>Age buckets · as of {data.as_of}</h2>
            </div>
            <div className="table-wrap" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th>DOCUMENT AGE</th>
                    <th className="right">RECEIVABLE</th>
                    <th className="right">PAYABLE</th>
                  </tr>
                </thead>
                <tbody>
                  {["0-30", "31-60", "61-90", "91+"].map((bucket) => (
                    <tr key={bucket}>
                      <td>{bucket} days</td>
                      <td className="right">
                        {rupees(data.buckets.receivable[bucket])}
                      </td>
                      <td className="right">
                        {rupees(data.buckets.payable[bucket])}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="panel register">
            <div className="panel-header">
              <h2>Open documents</h2>
            </div>
            <div className="table-wrap" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th>PARTY / DOCUMENT</th>
                    <th>TYPE</th>
                    <th>DATE</th>
                    <th className="right">AGE</th>
                    <th className="right">ORIGINAL</th>
                    <th className="right">APPLIED</th>
                    <th className="right">OUTSTANDING</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.document_id}>
                      <td>
                        {row.party}
                        <small className="bank-ref">{row.number}</small>
                        {row.due_date && (
                          <small className="bank-ref">
                            Due {row.due_date}
                            {row.overdue_days > 0
                              ? ` · ${row.overdue_days} days overdue`
                              : ""}
                          </small>
                        )}
                      </td>
                      <td>
                        {row.kind === "sales_invoice"
                          ? "Receivable"
                          : "Payable"}
                      </td>
                      <td>{row.date}</td>
                      <td className="right">{row.age_days} days</td>
                      <td className="right">{rupees(row.original_amount)}</td>
                      <td className="right">{rupees(row.applied_amount)}</td>
                      <td className="right">{rupees(row.outstanding)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!data.rows.length && (
                <div className="empty">
                  <strong>No open documents as of this date</strong>
                </div>
              )}
            </div>
          </section>
          <div className="info-box">
            {data.basis || 'Age buckets use the document date. Where entered, the due date and days overdue are shown separately. Payments and linked notes dated through the selected day reduce open amounts. Manual ledger adjustments are not allocated to individual documents.'}
          </div>
        </>
      )}
      {data &&
        view === "gst" &&
        Array.isArray(data.rows) &&
        (data.applicable ? (
          <>
            <div className="summary-grid">
              <Metric
                label="OUTWARD SUPPLY VALUE"
                value={data.totals.outward.taxable}
              />
              <Metric label="OUTPUT GST" value={data.totals.outward.tax} />
              <Metric
                label="INPUT PENDING REVIEW"
                value={data.totals.inward.pending_input}
              />
              <Metric
                label="GST IN COST"
                value={data.totals.inward.ineligible_input}
              />
            </div>
            <section className="panel register">
              <div className="panel-header">
                <h2>GST by supply class and rate</h2>
                <p>{data.document_count} posted GST documents in this period</p>
              </div>
              <div className="table-wrap" tabIndex={0}>
                <table>
                  <thead>
                    <tr>
                      <th>SIDE</th>
                      <th>CLASSIFICATION</th>
                      <th className="right">RATE</th>
                      <th className="right">SUPPLY VALUE</th>
                      <th className="right">TAX</th>
                      <th className="right">INPUT PENDING</th>
                      <th className="right">INPUT IN COST</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((row) => (
                      <tr key={`${row.side}-${row.treatment}-${row.gst_rate}`}>
                        <td>
                          {row.side === "outward" ? "Sales" : "Purchases"}
                        </td>
                        <td>{row.treatment.replaceAll("_", " ")}</td>
                        <td className="right">{row.gst_rate}%</td>
                        <td className="right">{rupees(row.taxable)}</td>
                        <td className="right">{rupees(row.tax)}</td>
                        <td className="right">{rupees(row.pending_input)}</td>
                        <td className="right">
                          {rupees(row.ineligible_input)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!data.rows.length && (
                  <div className="empty">
                    <strong>No posted GST documents in this period</strong>
                  </div>
                )}
              </div>
            </section>
            <div className="info-box">
              {data.note} Input tax is pending review, not a claimed credit.
              Credit and debit notes reduce the related totals.
            </div>
          </>
        ) : (
          <div className="info-box">
            This regular-GST analysis does not apply to the selected company
            profile or period. Composition and unregistered purchases can still
            show supplier GST included in cost in the purchase register.
          </div>
        ))}
      {data && view === "items" && Array.isArray(data.rows) && (
        <>
          <section className="panel register">
            <div className="panel-header">
              <h2>Item activity</h2>
            </div>
            <div className="table-wrap" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th>ITEM / HSN</th>
                    <th className="right">NET BEFORE PERIOD</th>
                    <th className="right">PURCHASED NET</th>
                    <th className="right">SOLD NET</th>
                    <th className="right">NET THROUGH END DATE</th>
                    <th className="right">SALES VALUE</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={`${row.name}-${row.hsn}`}>
                      <td>
                        {row.name}
                        <small className="bank-ref">{row.hsn}</small>
                      </td>
                      <td className="right">{row.opening_quantity}</td>
                      <td className="right">{row.purchased_quantity}</td>
                      <td className="right">{row.sold_quantity}</td>
                      <td className="right">{row.closing_quantity}</td>
                      <td className="right">{rupees(row.sales_value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!data.rows.length && (
                <div className="empty">
                  <strong>No posted item activity</strong>
                </div>
              )}
            </div>
          </section>
          <div className="info-box">
            Purchase/sales document movement only, grouped by description and HSN/SAC.
            Stock introductions and adjustments are excluded; these net quantities are not stock on hand.
            Use the tracked stock report for on-hand quantities and moving-average cost value.
          </div>
        </>
      )}
      {data && view === "stock" && Array.isArray(data.rows) && (
        <>
          <section className="panel register">
            <div className="panel-header">
              <h2>Tracked stock quantities</h2>
            </div>
            <div className="table-wrap" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th>ITEM / UNIT</th>
                    <th className="right">OPENING</th>
                    <th className="right">INTRODUCED</th>
                    <th className="right">ADJUSTMENTS NET</th>
                    <th className="right">PURCHASED NET</th>
                    <th className="right">SOLD NET</th>
                    <th className="right">CLOSING</th>
                    <th className="right">COST VALUE</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.item_id}>
                      <td>
                        {row.name}
                        <small className="bank-ref">{row.unit}</small>
                      </td>
                      <td className="right">{row.opening_quantity}</td>
                      <td className="right">{row.introduced_quantity}</td>
                      <td className="right">{row.adjustment_quantity}</td>
                      <td className="right">{row.purchased_quantity}</td>
                      <td className="right">{row.sold_quantity}</td>
                      <td className="right">{row.closing_quantity}</td>
                      <td className="right">
                        {row.closing_value === null
                          ? "Needs migration"
                          : rupees(row.closing_value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!data.rows.length && (
                <div className="empty">
                  <strong>No stock-tracked items</strong>
                </div>
              )}
            </div>
          </section>
          <div className="info-box">
            Only documents linked to stock-tracked item masters affect this
            report. A sale that would make stock negative is rejected. Opening
            stock can be posted once for an item before its first movement.
            Count adjustments are shown separately and post gains or losses to
            the ledger. Closing cost uses moving weighted average for newly
            tracked stock. Net realisable value adjustments and other valuation
            cases still need review.
          </div>
        </>
      )}
      {data &&
        ["sales", "purchases", "expenses"].includes(view) &&
        Array.isArray(data.rows) && (
          <>
            <div className="summary-grid">
              <Metric label="NET TOTAL" value={data.total} />
            </div>
            <section className="panel register report-register">
              <div className="panel-header">
                <h2>
                  {view === "sales"
                    ? "Sales"
                    : view === "expenses"
                      ? "Expense"
                      : "Purchase"}{" "}
                  register
                </h2>
              </div>
              <div className="table-wrap" tabIndex={0}>
                <table>
                  <thead>
                    <tr>
                      <th>DATE</th>
                      <th>DOCUMENT / PARTY</th>
                      <th>TYPE</th>
                      <th className="right">TAXABLE</th>
                      <th className="right">CGST</th>
                      <th className="right">SGST</th>
                      <th className="right">IGST</th>
                      <th className="right">SUPPLIER TAX</th>
                      <th className="right">GST IN COST</th>
                      <th className="right">TOTAL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((row, index) => (
                      <tr key={index}>
                        <td>{row.date}</td>
                        <td>
                          {row.number}
                          <small className="bank-ref">{row.party}</small>
                        </td>
                        <td>{row.kind.replaceAll("_", " ")}</td>
                        <td className="right">{rupees(row.taxable)}</td>
                        <td className="right">{rupees(row.cgst)}</td>
                        <td className="right">{rupees(row.sgst)}</td>
                        <td className="right">{rupees(row.igst)}</td>
                        <td className="right">{rupees(row.supplier_tax)}</td>
                        <td className="right">
                          {rupees(row.input_ineligible)}
                        </td>
                        <td className="right">{rupees(row.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!data.rows.length && (
                  <div className="empty">
                    <strong>No posted records in this period</strong>
                  </div>
                )}
              </div>
            </section>
          </>
        )}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="summary-card">
      <div className="summary-top">
        <span>{label}</span>
      </div>
      <FinancialFigure>{rupees(value)}</FinancialFigure>
    </div>
  );
}
function Line({ label, value }) {
  return (
    <div className="report-line">
      <span>{label}</span>
      <strong>{rupees(value)}</strong>
    </div>
  );
}
