import {sessionFetch as fetch} from './sessionScope.js';
import FinancialFigure from "./FinancialFigure.jsx";
import { businessDate } from "./businessDate.js";
import StatementImportPreview from "./StatementImportPreview.jsx";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Plus, Wallet, FileText, Search, ArrowDownLeft } from "lucide-react";
import CashBook from "./CashBook.jsx";
import CashTransfer from "./CashTransfer.jsx";

const money = (value) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(
    Number(value || 0),
  );
const auth = () => ({ Authorization: `Bearer ${localStorage.token}` });
async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: {
      ...auth(),
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
  const data = await response.json();
  if (!response.ok) {
    const error = Error(
      typeof data.detail === "string"
        ? data.detail
        : `Request failed (${response.status})`,
    );
    error.status = response.status;
    throw error;
  }
  return data;
}
function parseBankCsv(source) {
  const rows = [];
  let row = [],
    field = "",
    quoted = false;
  for (let i = 0; i < source.length; i++) {
    const ch = source[i];
    if (ch === '"') {
      if (quoted && source[i + 1] === '"') {
        field += '"';
        i++;
      } else quoted = !quoted;
    } else if (ch === "," && !quoted) {
      row.push(field);
      field = "";
    } else if ((ch === "\n" || ch === "\r") && !quoted) {
      if (ch === "\r" && source[i + 1] === "\n") i++;
      row.push(field);
      if (row.some((cell) => cell.trim())) rows.push(row);
      row = [];
      field = "";
    } else field += ch;
  }
  row.push(field);
  if (row.some((cell) => cell.trim())) rows.push(row);
  const headers = (rows.shift() || []).map((value, index) =>
    (index === 0 ? value.replace(/^\uFEFF/, "") : value).trim().toLowerCase(),
  );
  for (const required of ["date", "description", "amount"])
    if (!headers.includes(required))
      throw Error(`CSV needs a ${required} column`);
  return rows.map((cells, index) => {
    const value = (name) => cells[headers.indexOf(name)]?.trim() || "";
    const amount = value("amount");
    if (
      !/^\d{4}-\d{2}-\d{2}$/.test(value("date")) ||
      !/^[+-]?\d+(?:\.\d{1,2})?$/.test(amount) ||
      Number(amount) === 0
    )
      throw Error(`Invalid date or amount on CSV row ${index + 2}`);
    return {
      date: value("date"),
      description: value("description"),
      reference: value("reference"),
      amount,
    };
  });
}
function matchScore(line, record) {
  const text =
    `${line.reference || ""} ${line.description || ""}`.toLowerCase();
  const number = (record.number || "").toLowerCase();
  const name = (record.name || "").trim().toLowerCase();
  const days =
    Math.abs(
      Date.parse(`${line.date}T00:00:00Z`) -
        Date.parse(`${record.date}T00:00:00Z`),
    ) / 86400000;
  let score = 0;
  if (number && text.includes(number)) score += 80;
  if (Math.abs(Number(line.remaining_amount) - record.available) < 0.01)
    score += 40;
  if (name.length >= 4 && text.includes(name)) score += 20;
  if (days <= 2) score += 20;
  else if (days <= 7) score += 10;
  return score;
}
function Metric({ label, value, icon: Icon, count = false }) {
  return (
    <div className="summary-card">
      <div className="summary-top">
        <span>{label}</span>
        <Icon size={18} />
      </div>
      <FinancialFigure>{count ? value : money(value)}</FinancialFigure>
    </div>
  );
}

export default function BankWorkspace({ companyId, records, role, onSaved }) {
  const [banks, setBanks] = useState([
    { id: "default", name: "Bank clearing (legacy)", ledger_code: "SYS-BANK" },
  ]);
  const [bankId, setBankId] = useState("default");
  const [importFile,setImportFile] = useState(null),[importMessage,setImportMessage]=useState("");
  const [asOf, setAsOf] = useState(() =>
    businessDate(),
  );
  const [openingBalance, setOpeningBalance] = useState("0");
  const [lines, setLines] = useState([]);
  const [allLines, setAllLines] = useState([]);
  const [summary, setSummary] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [reviewNote, setReviewNote] = useState("");
  const [revision, setRevision] = useState(0);
  const [selected, setSelected] = useState({});
  const [allocationAmounts, setAllocationAmounts] = useState({});
  const [name, setName] = useState("");
  const [accountHint, setAccountHint] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const view = `${companyId}:${bankId}:${asOf}:${openingBalance}`;
  const activeView = useRef(view);
  activeView.current = view;
  useEffect(() => () => { activeView.current = null; }, []);
  const activeBank = banks.find((bank) => bank.id === bankId) || banks[0];

  useEffect(() => {
    if (!companyId) return;
    let active = true;
    setBankId("default");
    setBanks([
      {
        id: "default",
        name: "Bank clearing (legacy)",
        ledger_code: "SYS-BANK",
      },
    ]);
    setLines([]);
    setAllLines([]);
    setSummary(null);
    setReviews([]);
    setError("");
    api(`/companies/${companyId}/bank-accounts`)
      .then((data) => {
        if (active) setBanks(data);
      })
      .catch((err) => {
        if (active) setError(err.message);
      });
    return () => {
      active = false;
    };
  }, [companyId]);
  useEffect(() => {
    if (!companyId) return;
    let active = true;
    setLines([]);
    setAllLines([]);
    setSummary(null);
    setReviews([]);
    setSelected({});
    setAllocationAmounts({});
    const query = `?bank_account_id=${encodeURIComponent(bankId)}${asOf ? `&as_of=${encodeURIComponent(asOf)}` : ""}`;
    Promise.all([
      api(`/companies/${companyId}/bank-statement${query}`),
      api(
        `/companies/${companyId}/bank-reconciliation${query}&opening_balance=${encodeURIComponent(openingBalance || "0")}`,
      ),
      api(
        `/companies/${companyId}/bank-reconciliation/reviews?bank_account_id=${encodeURIComponent(bankId)}`,
      ),
      api(
        `/companies/${companyId}/bank-statement?bank_account_id=${encodeURIComponent(bankId)}`,
      ),
    ])
      .then(([items, totals, history, everyLine]) => {
        if (active) {
          setLines(items);
          setAllLines(everyLine);
          setSummary(totals);
          setReviews(history);
          setError("");
        }
      })
      .catch((err) => {
        if (active) setError(err.message);
      });
    return () => {
      active = false;
    };
  }, [companyId, bankId, asOf, openingBalance, revision, records.length]);

  async function createBank(event) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    const submittedView = view;
    setBusy(true);
    setError("");
    try {
      const bank = await api(`/companies/${companyId}/bank-accounts`, {
        method: "POST",
        body: JSON.stringify({ name, account_hint: accountHint }),
      });
      if (activeView.current !== submittedView) return;
      setBanks((current) => [...current, bank]);
      setBankId(bank.id);
      setName("");
      setAccountHint("");
    } catch (err) {
      if (activeView.current === submittedView) setError(err.message);
    } finally {
      inFlight.current = false;
      if (activeView.current !== null) setBusy(false);
    }
  }
  async function upload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setImportFile(file); event.target.value="";
  }
  async function allocate(line) {
    if (inFlight.current) return;
    inFlight.current = true;
    const submittedView = view;
    setBusy(true);
    setError("");
    try {
      await api(
        `/companies/${companyId}/bank-statement/${line.id}/allocations`,
        {
          method: "POST",
          body: JSON.stringify({
            record_id: selected[line.id],
            amount: allocationAmounts[line.id] || line.remaining_amount,
          }),
        },
      );
      if (activeView.current !== submittedView) return;
      setRevision((value) => value + 1);
    } catch (err) {
      if (activeView.current === submittedView) setError(err.message);
    } finally {
      inFlight.current = false;
      if (activeView.current !== null) setBusy(false);
    }
  }
  async function removeAllocation(allocation) {
    if (inFlight.current) return;
    inFlight.current = true;
    const submittedView = view;
    setBusy(true);
    setError("");
    try {
      await api(
        `/companies/${companyId}/bank-statement/allocations/${allocation.id}`,
        { method: "DELETE" },
      );
      if (activeView.current !== submittedView) return;
      setRevision((value) => value + 1);
    } catch (err) {
      if (activeView.current === submittedView) setError(err.message);
    } finally {
      inFlight.current = false;
      if (activeView.current !== null) setBusy(false);
    }
  }
  async function unmatch(line) {
    if (inFlight.current) return;
    inFlight.current = true;
    const submittedView = view;
    setBusy(true);
    setError("");
    try {
      await api(`/companies/${companyId}/bank-statement/${line.id}/match`, {
        method: "DELETE",
      });
      if (activeView.current !== submittedView) return;
      setRevision((value) => value + 1);
    } catch (err) {
      if (activeView.current === submittedView) setError(err.message);
    } finally {
      inFlight.current = false;
      if (activeView.current !== null) setBusy(false);
    }
  }
  async function saveReview(event) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    const submittedView = view;
    setBusy(true);
    setError("");
    try {
      const review = await api(
        `/companies/${companyId}/bank-reconciliation/reviews`,
        {
          method: "POST",
          body: JSON.stringify({
            bank_account_id: bankId,
            as_of: asOf,
            opening_balance: openingBalance || "0",
            note: reviewNote,
          }),
        },
      );
      if (activeView.current !== submittedView) return;
      setReviews((current) => [review, ...current]);
      setReviewNote("");
    } catch (err) {
      if (activeView.current === submittedView) setError(err.message);
    } finally {
      inFlight.current = false;
      if (activeView.current !== null) setBusy(false);
    }
  }
  const candidates = useMemo(() => {
    const used = new Map();
    for (const line of allLines)
      for (const allocation of line.allocations || [])
        used.set(
          allocation.record_id,
          (used.get(allocation.record_id) || 0) + Number(allocation.amount),
        );
    return records
      .filter(
        (record) =>
          record.posted &&
          !record.cancelled &&
          (!asOf || record.date <= asOf) &&
          [
            "payment_in",
            "payment_out",
            "expense",
            "bank_transfer",
            "pos",
            "customer_refund",
            "supplier_refund", "advance_refund",
          ].includes(record.kind) &&
          (record.kind === "bank_transfer" ||
            record.data?.payment_account === "bank") &&
          ((record.data?.bank_account_id || "default") === bankId || record.kind==="bank_transfer" && record.data?.direction==="bank_to_bank" && (record.data?.to_bank_account_id||"default")===bankId) &&
          !allLines.some((line) => line.matched_record_id === record.id),
      )
      .map((record) => ({
        ...record,
        available: Number(record.amount) - (used.get(record.id) || 0),
      }))
      .filter((record) => record.available > 0);
  }, [records, allLines, bankId, asOf]);
  function matchesDirection(record, amount) {
    const positive =
      record.kind === "payment_in" ||
      record.kind === "pos" ||
      record.kind === "supplier_refund" || record.kind === "advance_refund" && record.data?.payment_kind === "payment_out" ||
      (record.kind === "bank_transfer" &&
        (record.data?.direction === "cash_to_bank" || record.data?.direction === "bank_to_bank" && (record.data?.to_bank_account_id||"default")===bankId));
    return positive === (Number(amount) > 0);
  }
  function rankedCandidates(line) {
    return candidates
      .filter((record) => matchesDirection(record, line.amount))
      .map((record) => ({ record, score: matchScore(line, record) }))
      .sort(
        (a, b) =>
          b.score - a.score || b.record.date.localeCompare(a.record.date),
      );
  }
  function chooseRecord(line, recordId) {
    setSelected((current) => ({ ...current, [line.id]: recordId }));
    const available = candidates.find(
      (record) => record.id === recordId,
    )?.available;
    setAllocationAmounts((current) => ({
      ...current,
      [line.id]: available
        ? Math.min(Number(line.remaining_amount), available).toFixed(2)
        : line.remaining_amount,
    }));
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow green">CASH & BANK</div>
          <h1>Cash & bank</h1>
          <p>Track payments and reconcile each bank account separately.</p>
        </div>
        <label className="button primary upload-button">
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={upload}
            disabled={busy || !companyId || role === "viewer"}
          />
          <Plus size={16} />
          {busy ? "Working…" : "Import statement CSV"}
        </label>
      </div>
      <section className="panel settings-panel bank-accounts-panel">
        <div className="bank-account-heading">
          <div>
            <h2>Bank accounts</h2>
            <p>Choose the account for its balance, statement and matches.</p>
          </div>
          <label>
            Active bank
            <select
              className="form-select"
              value={bankId}
              onChange={(event) => setBankId(event.target.value)}
            >
              {banks.map((bank) => (
                <option key={bank.id} value={bank.id}>
                  {bank.name}
                  {bank.account_hint ? ` · ${bank.account_hint}` : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
        {role !== "viewer" && (
          <form className="bank-create-form" onSubmit={createBank}>
            <label>
              New bank account name
              <input
                required
                maxLength="120"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Operating account"
              />
            </label>
            <label>
              Account hint
              <input
                maxLength="32"
                value={accountHint}
                onChange={(event) => setAccountHint(event.target.value)}
                placeholder="Last four digits"
              />
            </label>
            <button className="button secondary" disabled={busy}>
              Add bank account
            </button>
          </form>
        )}
        <div className="bank-reconcile-filters">
          <label>
            Reconcile through
            <input
              type="date"
              value={asOf}
              onChange={(event) => setAsOf(event.target.value)}
            />
          </label>
          <label>
            Statement opening balance (₹)
            <input
              type="number"
              step="0.01"
              value={openingBalance}
              onChange={(event) => setOpeningBalance(event.target.value)}
            />
          </label>
          <p>
            Compare the imported statement closing balance with the posted bank
            ledger through this date.
          </p>
        </div>
      </section>
      <CashBook
        companyId={companyId}
        records={records}
        bankAccount={activeBank}
      />
      <CashTransfer
        preferredBankId={bankId}
        companyId={companyId}
        role={role}
        banks={banks}
        onSaved={() => {
          setRevision((value) => value + 1);
          onSaved();
        }}
      />
      {importFile&&<StatementImportPreview role={role} file={importFile} companyId={companyId} bankId={bankId} bankName={banks.find(b=>b.id===bankId)?.name||"Bank clearing"} api={api} onClose={()=>setImportFile(null)} onImported={async value=>{setImportMessage(`${value.added} transactions imported; ${value.duplicates} duplicates skipped.`);setRevision(v=>v+1)}}/>}{importMessage&&<p role="status">{importMessage}</p>}
      <div className="info-box bank-info">
        Map the date, description, reference and amount columns in your bank CSV. Separate debit and credit columns are supported. Positive
        amounts are received; negative amounts are paid. Import into the
        selected account. Payment suggestions use amount, date, reference and
        party name; confirm every allocation.
      </div>
      {error && <div className="error banner" role="alert">{error}</div>}
      {summary && (
        <div className="summary-grid bank-summary">
          <Metric
            label="STATEMENT CLOSING"
            value={summary.statement_closing_balance}
            icon={Wallet}
          />
          <Metric
            label="LEDGER CLOSING"
            value={summary.ledger_closing_balance}
            icon={FileText}
          />
          <Metric
            label="DIFFERENCE"
            value={summary.difference}
            icon={ArrowDownLeft}
          />
          <Metric
            label="UNMATCHED"
            value={summary.unmatched}
            icon={Search}
            count
          />
        </div>
      )}
      <section className="panel settings-panel">
        <h2>Reconciliation history</h2>
        <p>
          Save a dated review of the current statement and ledger balances.
          Reviews with a difference or unmatched lines need follow-up.
        </p>
        {summary && role !== "viewer" && (
          <form className="bank-create-form" onSubmit={saveReview}>
            <label>
              Review note
              <input
                maxLength="500"
                value={reviewNote}
                onChange={(event) => setReviewNote(event.target.value)}
                placeholder="Optional note about outstanding items"
              />
            </label>
            <button className="button secondary" disabled={busy || !asOf}>
              {busy ? "Saving…" : "Save review through " + asOf}
            </button>
          </form>
        )}
        <div className="ledger-list">
          {reviews.map((review) => (
            <div key={review.id}>
              <strong>
                {review.as_of} ·{" "}
                {review.status === "balanced" ? "Balanced" : "Needs review"}
              </strong>
              <span>
                Statement {money(review.statement_closing_balance)} · Ledger{" "}
                {money(review.ledger_closing_balance)} · Difference{" "}
                {money(review.difference)} · {review.unmatched} unmatched
                {review.note ? ` · ${review.note}` : ""}
              </span>
            </div>
          ))}
          {!reviews.length && <p>No saved reviews for this account.</p>}
        </div>
      </section>
      <section className="panel register bank-statement-panel">
        <div className="panel-header">
          <div>
            <h2>{activeBank.name} · statement lines</h2>
            <p>
              {lines.length} imported lines · allocate a statement amount across
              one or more posted payments
            </p>
          </div>
        </div>
        <div className="table-wrap" tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th>DATE</th>
                <th>DESCRIPTION</th>
                <th className="right">AMOUNT</th>
                <th>MATCH</th>
              </tr>
            </thead>
            <tbody>
              {lines.map((line) => (
                <tr key={line.id}>
                  <td>{line.date}</td>
                  <td>
                    <strong>{line.description}</strong>
                    <small className="bank-ref">{line.reference}</small>
                  </td>
                  <td className="right amount">{money(line.amount)}</td>
                  <td>
                    {line.matched_record_id ? (
                      <button
                        className="link"
                        disabled={busy || role === "viewer"}
                        onClick={() => unmatch(line)}
                      >
                        Matched · Unmatch
                      </button>
                    ) : (
                      <div className="bank-match-detail">
                        <div className="bank-allocation-status">
                          {Number(line.remaining_amount) === 0
                            ? "Fully matched"
                            : `${money(line.remaining_amount)} remaining`}
                        </div>
                        {line.allocations?.map((allocation) => (
                          <div
                            className="bank-allocation-row"
                            key={allocation.id}
                          >
                            <span>
                              {allocation.number ||
                                allocation.record_id.slice(0, 8)}{" "}
                              · {allocation.name} · {money(allocation.amount)}
                            </span>
                            {role !== "viewer" && (
                              <button
                                type="button"
                                className="link"
                                disabled={busy}
                                onClick={() => removeAllocation(allocation)}
                              >
                                Remove
                              </button>
                            )}
                          </div>
                        ))}
                        {Number(line.remaining_amount) > 0 &&
                          role !== "viewer" && (
                            <div className="bank-match">
                              <select
                                className="form-select"
                                aria-label={`Payment for ${line.description}`}
                                value={selected[line.id] || ""}
                                disabled={busy}
                                onChange={(event) =>
                                  chooseRecord(line, event.target.value)
                                }
                              >
                                <option value="">Choose payment</option>
                                {rankedCandidates(line).map(
                                  ({ record, score }) => (
                                    <option value={record.id} key={record.id}>
                                      {score >= 50 ? "Suggested · " : ""}
                                      {record.number ||
                                        record.id.slice(0, 8)} · {record.name} ·{" "}
                                      {money(record.available)} available
                                    </option>
                                  ),
                                )}
                              </select>
                              <input
                                className="form-input"
                                aria-label={`Amount to match for ${line.description}`}
                                type="number"
                                min="0.01"
                                max={line.remaining_amount}
                                step="0.01"
                                value={
                                  allocationAmounts[line.id] ??
                                  line.remaining_amount
                                }
                                onChange={(event) =>
                                  setAllocationAmounts({
                                    ...allocationAmounts,
                                    [line.id]: event.target.value,
                                  })
                                }
                              />
                              <button
                                className="button secondary"
                                disabled={
                                  !selected[line.id] ||
                                  busy ||
                                  Number(
                                    allocationAmounts[line.id] ??
                                      line.remaining_amount,
                                  ) <= 0 ||
                                  Number(
                                    allocationAmounts[line.id] ??
                                      line.remaining_amount,
                                  ) > Number(line.remaining_amount) ||
                                  Number(
                                    allocationAmounts[line.id] ??
                                      line.remaining_amount,
                                  ) >
                                    Number(
                                      candidates.find(
                                        (record) =>
                                          record.id === selected[line.id],
                                      )?.available || 0,
                                    )
                                }
                                onClick={() => allocate(line)}
                              >
                                Allocate
                              </button>
                            </div>
                          )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!lines.length && (
            <div className="empty">
              <strong>No statement imported for this account</strong>
            </div>
          )}
        </div>
      </section>
    </>
  );
}
