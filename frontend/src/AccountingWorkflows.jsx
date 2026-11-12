import { businessDate } from "./businessDate.js";
import { usePostingRequest, pendingPostingMessage } from "./usePostingRequest.js";
import React, { useEffect, useRef, useState } from "react";
const today = () => businessDate();
const money = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(
    Number(n || 0),
  );
function useBalanceRefresh(refresh) {
  const inFlight = useRef(false);
  const live = useRef(true);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  async function run() {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError('');
    try { await refresh(); }
    catch (reason) { if (live.current) setError(reason.message); }
    finally { inFlight.current = false; if (live.current) setBusy(false); }
  }
  return { run, busy, error };
}
function BalanceRefreshNotice({state}) {
  return state.error && <div className="info-box" role="alert">The posting was confirmed, but balances could not refresh: {state.error}.<button type="button" disabled={state.busy} onClick={state.run}>Refresh balances</button></div>;
}
export function CreditSettlements({
  companyId,
  kind,
  records,
  api,
  refresh,
  canWrite,
}) {
  const notes = records.filter(
    (r) =>
      r.kind === (kind === "payment_in" ? "credit_note" : "debit_note") &&
      Number(r.credit_remaining) > 0,
  );
  const [form, setForm] = useState({
      note: "",
      action: "apply",
      target: "",
      amount: "",
      date: today(),
      account: "cash",
      bank: "default",
    }),
    [banks, setBanks] = useState([]),
    [error, setError] = useState(""),
    [requestKey, setRequestKey] = useState(() => crypto.randomUUID());
  const posting = usePostingRequest();
  const flow = useRef(false);
  const balanceRefresh = useBalanceRefresh(refresh);
  const [success, setSuccess] = useState("");
  const { busy, pending } = posting;
  useEffect(() => {
    let live = true;
    api(`/companies/${companyId}/bank-accounts`)
      .then((r) => {
        if (live) setBanks(r);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [companyId, api]);
  const note = notes.find((n) => n.id === form.note),
    targets = records.filter(
      (r) =>
        r.kind ===
          (kind === "payment_in" ? "sales_invoice" : "purchase_bill") &&
        r.posted &&
        Number(r.outstanding) > 0 &&
        r.name.toLowerCase() === note?.name.toLowerCase(),
    );
  async function submit(e) {
    e.preventDefault();
    if (!canWrite || flow.current || balanceRefresh.busy || (!pending && !note)) return;
    flow.current = true; setSuccess("");
    setError("");
    try {
      const path = `/companies/${companyId}/credits/${note?.id}/settle`;
      const options = {
        method: "POST",
        headers: { "Idempotency-Key": requestKey },
        body: JSON.stringify({
          kind: "credit",
          date: form.date,
          amount: form.amount,
          data: {
            action: form.action,
            applied_to: form.target,
            payment_account: form.account,
            bank_account_id: form.bank,
          },
        }),
      };
      if (!await posting.run(() => api(path, options))) return;
      setSuccess("Credit settlement saved.");
      setForm({ ...form, note: "", amount: "", target: "" });
      setRequestKey(crypto.randomUUID());
      await balanceRefresh.run();
    } catch (e) {
      setError(e.message);
    } finally { flow.current = false; }
  }
  if (!notes.length && !success && !pending) return null;
  return (
    <section className="panel settings-panel">
      <h2>
        {kind === "payment_in"
          ? "Customer credits and refunds"
          : "Supplier credits and refunds"}
      </h2>
      <p>
        Apply an unused note balance to another document or record a refund.
      </p>
      {canWrite && (
        <form className="form-grid" onSubmit={submit}>
          <fieldset className="form-grid full submission-fields" disabled={busy || pending || balanceRefresh.busy || !canWrite}>
          <label>
            Credit balance
            <select
              required
              className="form-select"
              value={form.note}
              onChange={(e) =>
                setForm({
                  ...form,
                  note: e.target.value,
                  target: "",
                  amount: "",
                })
              }
            >
              <option value="">Choose a note</option>
              {notes.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.number} · {n.name} · {money(n.credit_remaining)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Action
            <select
              className="form-select"
              value={form.action}
              onChange={(e) => setForm({ ...form, action: e.target.value })}
            >
              <option value="apply">Apply to another document</option>
              <option value="refund">Record refund</option>
            </select>
          </label>
          {form.action === "apply" ? (
            <label className="full">
              Document
              <select
                className="form-select"
                required
                value={form.target}
                onChange={(e) => setForm({ ...form, target: e.target.value })}
              >
                <option value="">Choose an outstanding document</option>
                {targets.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.number} · {money(r.outstanding)}
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
                  value={form.account}
                  onChange={(e) =>
                    setForm({ ...form, account: e.target.value })
                  }
                >
                  <option value="cash">Cash</option>
                  <option value="bank">Bank</option>
                </select>
              </label>
              {form.account === "bank" && (
                <label>
                  Bank account
                  <select
                    className="form-select"
                    value={form.bank}
                    onChange={(e) => setForm({ ...form, bank: e.target.value })}
                  >
                    {banks.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </>
          )}
          <label>
            Amount
            <input
              required
              type="number"
              min="0.01"
              step="0.01"
              max={note?.credit_remaining}
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
          </label>
          <label>
            Date
            <input
              required
              type="date"
              min={note?.date}
              value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })}
            />
          </label>
          </fieldset>
          {pending && !busy && <p className="info-box full" role="status">{pendingPostingMessage}</p>}
          <button className="button primary full" disabled={busy || balanceRefresh.busy || (!note && !pending)}>
            {busy
              ? "Saving…"
              : form.action === "apply"
                ? "Apply credit"
                : "Record refund"}
          </button>
        </form>
      )}
      {success && <p role="status">{success}</p>}
      <BalanceRefreshNotice state={balanceRefresh} />
      {error && (
        <div className="error banner" role="alert">
          {error}
        </div>
      )}
    </section>
  );
}
export function OpeningBalances({ companyId, records, api, refresh, role }) {
  const [form, setForm] = useState({
      type: "receivable",
      party: "",
      bank: "default",
      amount: "",
      date: today(),
      overdraft: false,
    }),
    [banks, setBanks] = useState([]),
    [error, setError] = useState(""),
    [success, setSuccess] = useState(""),
    [key, setKey] = useState(() => crypto.randomUUID());
  const posting = usePostingRequest();
  const { busy, pending } = posting;
  const flow = useRef(false);
  const balanceRefresh = useBalanceRefresh(refresh);
  useEffect(() => {
    let live = true;
    api(`/companies/${companyId}/bank-accounts`)
      .then((r) => {
        if (live) setBanks(r);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [companyId, api]);
  if (role !== "owner") return null;
  async function submit(e) {
    e.preventDefault();
    if (role !== "owner" || flow.current || balanceRefresh.busy) return;
    flow.current = true;
    setError("");
    setSuccess("");
    try {
      const path = `/companies/${companyId}/opening-balances`;
      const options = {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify({
          kind: "opening",
          date: form.date,
          amount: form.amount,
          data: {
            balance_kind: form.type,
            party_id: form.party,
            bank_account_id: form.bank,
            overdraft: form.overdraft,
          },
        }),
      };
      if (!await posting.run(() => api(path, options))) return;
      setSuccess("Opening balance posted to the ledger.");
      setKey(crypto.randomUUID());
      setForm({ ...form, amount: "" });
      await balanceRefresh.run();
    } catch (e) {
      setError(e.message);
    } finally {
      flow.current = false;
    }
  }
  return (
    <section className="member-settings">
      <h2>Opening balances</h2>
      <p>
        Set balances before the first transaction for that party or cash/bank
        account. Opening stock is available in Items.
      </p>
      <form className="form-grid" onSubmit={submit}>
        <fieldset className="form-grid full submission-fields" disabled={busy || pending || balanceRefresh.busy}>
        <label>
          Balance type
          <select
            className="form-select"
            value={form.type}
            onChange={(e) =>
              setForm({ ...form, type: e.target.value, overdraft: false })
            }
          >
            <option value="receivable">Customer owes us</option>
            <option value="payable">We owe supplier</option>
            <option value="cash">Cash in hand</option>
            <option value="bank">Bank balance</option>
          </select>
        </label>
        {["receivable", "payable"].includes(form.type) && (
          <label>
            Party
            <select
              required
              className="form-select"
              value={form.party}
              onChange={(e) => setForm({ ...form, party: e.target.value })}
            >
              <option value="">Choose a party</option>
              {records
                .filter((r) => r.kind === "party")
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
            </select>
          </label>
        )}
        {form.type === "bank" && (
          <>
            <label>
              Bank account
              <select
                className="form-select"
                value={form.bank}
                onChange={(e) => setForm({ ...form, bank: e.target.value })}
              >
                {banks.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={form.overdraft}
                onChange={(e) =>
                  setForm({ ...form, overdraft: e.target.checked })
                }
              />
              Overdraft (credit balance)
            </label>
          </>
        )}
        <label>
          As of date
          <input
            type="date"
            required
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
          />
        </label>
        <label>
          Amount
          <input
            required
            type="number"
            min="0.01"
            step="0.01"
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
          />
        </label>
        </fieldset>
        {pending && !busy && <p className="info-box full" role="status">{pendingPostingMessage}</p>}
        <button className="button primary full" disabled={busy || balanceRefresh.busy}>
          {busy ? "Posting…" : "Post opening balance"}
        </button>
      </form>
      {error && (
        <div className="error banner" role="alert">
          {error}
        </div>
      )}
      {success && <p role="status">{success}</p>}
      <BalanceRefreshNotice state={balanceRefresh} />
    </section>
  );
}
