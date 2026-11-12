import {createRequestScope} from './requestScope.js';
import {useBalanceRefresh, BalanceRefreshNotice} from './postingRefresh.jsx';
import {sessionFetch as fetch, captureSession} from './sessionScope.js';
import { businessDate } from "./businessDate.js";
import { usePostingRequest, pendingPostingMessage } from "./usePostingRequest.js";
import React, { useRef, useState } from "react";
import { downloadBlob } from "./downloadBlob.js";

const money = (value) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(
    Number(value || 0),
  );
const today = () => businessDate();

export default function Advances({
  companyId,
  kind,
  records,
  api,
  refresh,
  canWrite,
}) {
  const [banks, setBanks] = useState([]);
  React.useEffect(() => {
    let live = true;
    api(`/companies/${companyId}/bank-accounts`)
      .then((rows) => {
        if (live) setBanks(rows);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [companyId, api]);
  const [selected, setSelected] = useState("");
  const [form, setForm] = useState({
    date: today(),
    target: "",
    amount: "",
    action: "apply",
    payment_account: "cash",
    bank_account_id: "default",
  });
  const [key, setKey] = useState(() => crypto.randomUUID());
  const posting = usePostingRequest();
  const { busy, pending } = posting;
  const flow = useRef(false);
  const balanceRefresh = useBalanceRefresh(refresh);
  const [success, setSuccess] = useState("");
  const [error, setError] = useState("");
  const [asOf, setAsOf] = useState(today);
  const exportContext = JSON.stringify([companyId, kind, asOf]);
  const exportScope = useRef(createRequestScope(exportContext)); exportScope.current.setContext(exportContext);
  React.useEffect(() => () => exportScope.current.setContext(Symbol('unmounted')), []);
  async function download(fmt) {
    if (!asOf) return;
    const current = exportScope.current.capture();
    setError("");
    try {
      const verifySession = captureSession();
      const response = await fetch(
        `/api/companies/${companyId}/reports/advances.${fmt}?as_of=${encodeURIComponent(asOf)}`,
        { headers: { Authorization: `Bearer ${localStorage.token}` } },
      );
      if (!response.ok) throw Error("Advance report could not be exported");
      const blob = await response.blob();
      if (!current()) return;
      verifySession();
      downloadBlob(blob, `apex-advances.${fmt}`);
    } catch (reason) {
      if (current()) setError(reason.message);
    }
  }
  const advances = records.filter(
    (row) => row.kind === kind && !row.cancelled && row.advance_remaining != null,
  );
  const advance = advances.find((row) => row.id === selected);
  const applications = records.filter(
    (row) =>
      ["advance_application", "advance_refund"].includes(row.kind) &&
      row.data?.advance_id === selected,
  );
  const targets = records.filter(
    (row) =>
      row.kind ===
        (kind === "payment_in" ? "sales_invoice" : "purchase_bill") &&
      row.posted &&
      !row.cancelled &&
      Number(row.outstanding) > 0 &&
      row.name.trim().toLowerCase() === advance?.name.trim().toLowerCase(),
  );
  const target = targets.find(row => row.id === form.target);
  const earliestDate = [advance?.date, form.action === "apply" ? target?.date : null].filter(Boolean).sort().at(-1);
  function change(value) {
    setForm((current) => ({ ...current, ...value }));
    setKey(crypto.randomUUID());
    setError("");
  }
  async function submit(event) {
    event.preventDefault();
    if (!canWrite || flow.current || balanceRefresh.busy || (!pending && !advance)) return;
    flow.current = true; setSuccess("");
    setError("");
    try {
      const path = `/companies/${companyId}/advances/${selected}/${form.action}`;
      const options = {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify({
          kind: "advance_application",
          name: advance?.name,
          date: form.date,
          amount: form.amount,
          data: {
            applied_to: form.target,
            payment_account: form.payment_account,
            bank_account_id: form.bank_account_id,
          },
        }),
      };
      if (!await posting.run(() => api(path, options))) return;
      setSuccess("Advance settlement saved.");
      setForm({
        date: today(),
        target: "",
        amount: "",
        action: "apply",
        payment_account: "cash",
        bank_account_id: "default",
      });
      setKey(crypto.randomUUID());
      await balanceRefresh.run();
    } catch (reason) {
      setError(reason.message);
    } finally { flow.current = false; }
  }
  if (!advances.length && !pending && !success) return null;
  return (
    <section className="panel settings-panel">
      <h2>{kind === "payment_in" ? "Customer" : "Supplier"} advances</h2>
      <p>
        Available advances stay separate from invoice balances until applied.
        Select a payment to view its history.
      </p>
      <div className="form-grid">
        <label>
          Report as of
          <input
            type="date"
            required
            value={asOf}
            onChange={(event) => setAsOf(event.target.value)}
          />
        </label>
        <div>
          <button
            type="button"
            className="button secondary"
            disabled={!asOf}
            onClick={() => download("xlsx")}
          >
            XLSX
          </button>{" "}
          <button
            type="button"
            className="button secondary"
            disabled={!asOf}
            onClick={() => download("pdf")}
          >
            PDF
          </button>
        </div>
      </div>
      {success && <p role="status">{success}</p>}
      <BalanceRefreshNotice state={balanceRefresh} />
      {pending && !busy && <p className="info-box" role="status">{pendingPostingMessage}</p>}
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <label>
        Advance payment
        <select
          className="form-select"
          disabled={busy || pending || balanceRefresh.busy}
          value={selected}
          onChange={(event) => {
            setSelected(event.target.value);
            change({ target: "", amount: "" });
          }}
        >
          <option value="">Choose payment</option>
          {advances.map((row) => (
            <option key={row.id} value={row.id}>
              {row.number} · {row.name} · {money(row.advance_remaining)}{" "}
              available
            </option>
          ))}
        </select>
      </label>
      {(advance || pending) && (
        <>
          {advance && <p>
            Original {money(advance.amount)} · Available{" "}
            {money(advance.advance_remaining)}
          </p>}
          {applications.map((row) => (
            <p key={row.id}>
              {row.date} ·{" "}
              {records.find((item) => item.id === row.data.applied_to)
                ?.number ||
                (row.kind === "advance_refund" ? "Refund" : "Document")}{" "}
              · {money(row.amount)}
            </p>
          ))}
          {canWrite && (pending || Number(advance?.advance_remaining) > 0) && (
            <form className="form-grid" onSubmit={submit}>
              <fieldset className="form-grid full submission-fields" disabled={busy || pending || balanceRefresh.busy}>
              <label>
                Date
                <input
                  type="date"
                  required
                  min={earliestDate}
                  value={form.date}
                  disabled={busy || pending || balanceRefresh.busy}
                  onChange={(event) => change({ date: event.target.value })}
                />
                {earliestDate && <small>On or after {earliestDate}, when both source documents exist.</small>}
              </label>
              <label>
                Action
                <select
                  className="form-select"
                  aria-label="Advance action"
                  value={form.action}
                  onChange={(event) =>
                    change({ action: event.target.value, target: "" })
                  }
                >
                  <option value="apply">Apply to document</option>
                  <option value="refund">Record refund</option>
                </select>
              </label>
              {form.action === "apply" ? (
                <label>
                  Invoice or bill
                  <select
                    className="form-select"
                    required
                    value={form.target}
                    disabled={busy || pending || balanceRefresh.busy}
                    onChange={(event) => change({ target: event.target.value })}
                  >
                    <option value="">Choose document</option>
                    {targets.map((row) => (
                      <option key={row.id} value={row.id}>
                        {row.number} · {money(row.outstanding)} due
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <>
                  <label>
                    Refund account
                    <select
                      className="form-select"
                      aria-label="Advance refund account"
                      value={form.payment_account}
                      onChange={(event) =>
                        change({ payment_account: event.target.value })
                      }
                    >
                      <option value="cash">Cash</option>
                      <option value="bank">Bank</option>
                    </select>
                  </label>
                  {form.payment_account === "bank" && (
                    <label>
                      Bank account
                      <select
                        className="form-select"
                        aria-label="Advance refund bank"
                        value={form.bank_account_id}
                        onChange={(event) =>
                          change({ bank_account_id: event.target.value })
                        }
                      >
                        {banks.map((bank) => (
                          <option key={bank.id} value={bank.id}>
                            {bank.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                </>
              )}
              <label>
                Amount (₹)
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  max={advance ? Math.min(
                    Number(advance.advance_remaining),
                    Number(
                      targets.find((row) => row.id === form.target)
                        ?.outstanding || advance.advance_remaining,
                    ),
                  ) : undefined}
                  required
                  disabled={busy || pending || balanceRefresh.busy}
                  value={form.amount}
                  onChange={(event) => change({ amount: event.target.value })}
                />
              </label>
              </fieldset>
              <button
                className="button primary"
                disabled={busy || balanceRefresh.busy || (!pending && form.action === "apply" && !targets.length)}
              >
                {busy
                  ? "Saving…"
                  : form.action === "apply"
                    ? "Apply advance"
                    : "Record advance refund"}
              </button>
            </form>
          )}
        </>
      )}
    </section>
  );
}
