import React, { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, PackageCheck } from "lucide-react";
import { businessDate } from "./businessDate.js";
import { pendingPostingMessage, usePostingRequest } from "./usePostingRequest.js";
import { companyRequestRecovery } from "./companyRequestRecovery.js";
import { registerPostingRequest } from "./postingRegistry.js";

const money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
const statusNames = { open: "Awaiting delivery", partial: "Partially received", received: "Fully received", converted: "Converted to bill", unavailable: "Full-order billing" };
const taxTreatments = { taxable: "Taxable", nil_rated: "Nil rated", exempt: "Exempt", non_gst: "Non-GST" };
const inputCredit = { pending_review: "Pending ITC review", ineligible: "Ineligible ITC" };
const editableFields = ["rate", "gst_rate", "tax_treatment", "price_includes_tax", "itc_treatment", "discount_amount"];

export default function PurchaseOrderReceiving({ order, companyId, taxMode, writable, api, onOpen, onRefresh, onStatus }) {
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadRevision, reload] = useState(0);
  const [editing, setEditing] = useState(false);
  const [date, setDate] = useState(businessDate);
  const [number, setNumber] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [notes, setNotes] = useState("");
  const [entries, setEntries] = useState({});
  const [quote, setQuote] = useState(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(null);
  const [recovery] = useState(() => {
    try {
      const store = companyRequestRecovery(companyId, globalThis.localStorage?.token, window.sessionStorage, "purchase-receipt");
      const command = store?.read();
      return { store, command: command?.orderId === order.id ? command : null, otherOrder: command?.orderId !== order.id ? command?.orderId : null };
    } catch (failure) {
      return { error: failure.message };
    }
  });
  const operation = useRef(recovery.command);
  const formHeading = useRef(null);
  const posting = usePostingRequest({ definitiveRetryCodes: ["PO_RECEIPT_REVIEW_REQUIRED"] });
  const { busy } = posting;
  const pending = !!operation.current || posting.pending;
  const base = `/companies/${companyId}/purchase-orders/${order.id}`;

  useEffect(() => registerPostingRequest({ get pending() { return !!operation.current; } }), []);

  useEffect(() => {
    const controller = new AbortController();
    api(`${base}/receiving`, { signal: controller.signal }).then(result => {
      if (!controller.signal.aborted) {
        setSnapshot(result);
        setLoading(false);
        onStatus?.(result);
      }
    }).catch(failure => {
      if (!controller.signal.aborted) { setError(failure.message); setLoading(false); }
    });
    return () => controller.abort();
  }, [api, base, loadRevision, onStatus]);

  useEffect(() => {
    if (editing) formHeading.current?.focus();
  }, [editing]);

  const selection = useMemo(() => (snapshot?.lines || []).flatMap(row => {
    const entry = entries[row.line_index];
    if (!(Number(entry?.quantity) > 0)) return [];
    const overrides = Object.fromEntries(editableFields
      .filter(field => entry[field] !== "" && entry[field] != null)
      .map(field => [field, entry[field]]));
    return [{ line_index: row.line_index, quantity: entry.quantity, ...overrides }];
  }), [snapshot, entries]);
  const invalidQuantity = snapshot?.lines.some(row => {
    const quantity = entries[row.line_index]?.quantity;
    return quantity && (!/^\d+(?:\.\d{1,3})?$/.test(quantity) || Number(quantity) > Number(row.remaining_quantity));
  });
  const payload = useMemo(() => ({
    source_version: snapshot?.source_version,
    date,
    ...(number.trim() ? { number: number.trim() } : {}),
    ...(dueDate ? { due_date: dueDate } : {}),
    ...(notes.trim() ? { notes: notes.trim() } : {}),
    lines: selection,
  }), [snapshot, date, number, dueDate, notes, selection]);
  const canReceive = !pending && !recovery.error && !recovery.otherOrder && !!snapshot?.lines?.some(row => Number(row.remaining_quantity) > 0) &&
    ["open", "partial"].includes(snapshot?.status) && writable;
  const canQuote = editing && !loading && canReceive && selection.length > 0 && !invalidQuantity &&
    date >= order.date && date <= businessDate() && (!dueDate || dueDate >= date);
  const currentQuote = quote?.payload === payload ? quote : null;

  useEffect(() => {
    if (!canQuote || pending) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api(`${base}/receipts/preview`, { method: "POST", signal: controller.signal, body: JSON.stringify(payload) })
        .then(result => { if (!controller.signal.aborted) setQuote({ payload, amount: result.amount }); })
        .catch(failure => { if (!controller.signal.aborted) setQuote({ payload, error: failure.message }); });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [api, base, canQuote, payload, pending]);

  function update(index, field, value) {
    setEntries(previous => ({
      ...previous,
      [index]: {
        ...previous[index],
        [field]: value,
        ...(field === "tax_treatment" && value && value !== "taxable" ? { gst_rate: "0" } : {}),
      },
    }));
    setError("");
  }

  function refresh() {
    setLoading(true);
    setError("");
    reload(value => value + 1);
  }

  async function post(event) {
    event?.preventDefault();
    const retrying = !!operation.current;
    if (!writable || busy || recovery.error || (!retrying && (!canQuote || !currentQuote?.amount || Number(currentQuote.amount) <= 0))) return;
    setError("");
    try {
      if (!retrying) {
        const command = { key: crypto.randomUUID(), orderId: order.id, body: JSON.stringify({ ...payload, expected_total: currentQuote.amount }) };
        recovery.store?.save(command);
        operation.current = command;
      }
      const command = operation.current;
      const result = await posting.run(() => api(`${base}/receipts`, {
        method: "POST", headers: { "Idempotency-Key": command.key }, body: command.body,
      }));
      if (!result) return;
      recovery.store?.clear(command.key);
      operation.current = null;
      setSaved(result.value);
      setEditing(false);
      setEntries({});
      setNumber("");
      setDueDate("");
      setNotes("");
      refresh();
      await onRefresh?.();
    } catch (failure) {
      if (operation.current && !posting.isPending() &&
          ((!retrying && failure.status >= 400 && failure.status < 500 && failure.status !== 408) || failure.code === "PO_RECEIPT_REVIEW_REQUIRED")) {
        recovery.store?.clear(operation.current.key);
        operation.current = null;
        if (failure.status === 409) { setEntries({}); refresh(); }
      }
      setError(failure.message);
    }
  }

  return <section className="detail-section purchase-receiving" aria-label="Purchase order receiving">
    <div className="detail-section-heading">
      <h3>Receiving</h3>
      {snapshot?.status && <span>{statusNames[snapshot.status]}</span>}
    </div>
    {loading && <p role="status">Checking order balances…</p>}
    {recovery.error && <p className="error" role="alert">{recovery.error}</p>}
    {recovery.otherOrder && <div className="info-box">
      A supplier bill on another order is awaiting confirmation.
      <button type="button" className="button secondary" onClick={() => onOpen({ id: recovery.otherOrder })}>Open pending order</button>
    </div>}
    {error && <p className="error" role="alert">{error}</p>}
    {error && !busy && !pending && <button type="button" className="button secondary" onClick={refresh}>Refresh order quantities</button>}
    {saved && <div className="info-box purchase-receiving-success" role="status">
      <strong><PackageCheck size={18} aria-hidden="true" /> {saved.posted === false ? `Bill ${saved.number} was cancelled` : `Stock received on bill ${saved.number}`}</strong>
      <button type="button" className="button secondary" onClick={() => onOpen(saved)}>View purchase bill<ArrowRight size={16} /></button>
    </div>}
    {snapshot?.status === "unavailable" && <p>{snapshot.reason}</p>}
    {pending && !editing && <div className="info-box purchase-receiving-success" role="status">
      <p>The previous response was not confirmed. Retry the original bill to recover its result.</p>
      <button type="button" className="button primary" disabled={busy || !writable} onClick={() => post()}>{busy ? "Recovering bill…" : "Retry bill"}</button>
    </div>}
    {snapshot && !["converted", "unavailable"].includes(snapshot.status) && !editing && !pending && <div className="purchase-receiving-balances">
      {snapshot.lines.map(row => <div key={row.line_index} className="purchase-receiving-line">
        <div><strong>{row.description}</strong><small>Ordered {row.ordered_quantity} · Received {row.received_quantity}</small></div>
        <span>{row.remaining_quantity} {row.unit || "units"} left</span>
      </div>)}
      {canReceive && <button type="button" className="button primary" disabled={loading} onClick={() => { setSaved(null); setEditing(true); }}>Receive items</button>}
    </div>}
    {snapshot && editing && <form className="form-grid purchase-receiving-form" onSubmit={post}>
      <fieldset className="form-grid full submission-fields" disabled={busy || pending || !writable || loading}>
        <legend ref={formHeading} tabIndex={-1}>Receive a delivery</legend>
        <p className="full">Enter items from this delivery. Posting creates the supplier bill and adds tracked goods to stock.</p>
        <label>Bill date<input type="date" required min={order.date} max={businessDate()} value={date} onChange={event => setDate(event.target.value)} /></label>
        <label>Supplier bill number<input maxLength={16} value={number} onChange={event => setNumber(event.target.value)} placeholder="Auto-number if blank" /></label>
        <label>Due date<input type="date" min={date} value={dueDate} onChange={event => setDueDate(event.target.value)} /></label>
        <label>Notes<input maxLength={500} value={notes} onChange={event => setNotes(event.target.value)} /></label>
        {snapshot.lines.filter(row => Number(row.remaining_quantity) > 0).map(row => (
          <div key={row.line_index} className="purchase-receiving-delivery full">
            <strong>{row.description}</strong>
            <p>Order line {row.line_index + 1} · {row.remaining_quantity} {row.unit || "units"} left</p>
            <div className="form-grid">
              <label>Received now<input aria-label={`Received quantity for ${row.description} (line ${row.line_index + 1})`}
                type="number" min="0" max={row.remaining_quantity} step="0.001" value={entries[row.line_index]?.quantity || ""}
                onChange={event => update(row.line_index, "quantity", event.target.value)} /></label>
              <label>Unit price (₹)<input aria-label={`Unit price for ${row.description} (line ${row.line_index + 1})`}
                type="number" min="0" step="0.01" placeholder={row.rate} value={entries[row.line_index]?.rate ?? ""}
                onChange={event => update(row.line_index, "rate", event.target.value)} /></label>
            </div>
            {Number(entries[row.line_index]?.quantity) > 0 && <details className="purchase-receiving-tax">
              <summary>Supplier tax and discount</summary>
              <p>These values default to the purchase order. Review them against the supplier bill.</p>
              <div className="form-grid">
                <label>Tax classification
                  <select className="form-select" value={entries[row.line_index]?.tax_treatment ?? ""} onChange={event => update(row.line_index, "tax_treatment", event.target.value)}>
                    <option value="">Use order · {taxTreatments[row.tax_treatment || "taxable"]}</option>
                    {Object.entries(taxTreatments).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>
                <label>GST rate (%)
                  <input type="number" min="0" max="100" step="0.01" placeholder={row.gst_rate ?? "0"} value={entries[row.line_index]?.gst_rate ?? ""}
                    onChange={event => update(row.line_index, "gst_rate", event.target.value)} />
                </label>
                <label>Unit price tax basis
                  <select className="form-select" value={entries[row.line_index]?.price_includes_tax == null ? "" : String(entries[row.line_index].price_includes_tax)}
                    onChange={event => update(row.line_index, "price_includes_tax", event.target.value === "" ? null : event.target.value === "true")}>
                    <option value="">Use order · {row.price_includes_tax ? "Includes GST" : "Excludes GST"}</option>
                    <option value="true">Includes GST</option><option value="false">Excludes GST</option>
                  </select>
                </label>
                {taxMode === "regular" && <label>Input credit treatment
                  <select className="form-select" value={entries[row.line_index]?.itc_treatment ?? ""} onChange={event => update(row.line_index, "itc_treatment", event.target.value)}>
                    <option value="">Use order · {inputCredit[row.itc_treatment || "pending_review"]}</option>
                    {Object.entries(inputCredit).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                </label>}
                <label>Discount on received line (₹)
                  <input type="number" min="0" step="0.01" placeholder="Use order discount" value={entries[row.line_index]?.discount_amount ?? ""}
                    onChange={event => update(row.line_index, "discount_amount", event.target.value)} />
                </label>
              </div>
            </details>}
          </div>
        ))}
      </fieldset>
      {invalidQuantity && <p className="error full" role="alert">Use a quantity within the remaining amount for each order line.</p>}
      {currentQuote?.error && <p className="error full" role="alert">{currentQuote.error}</p>}
      {canQuote && !currentQuote && <p className="full" role="status">Checking bill total…</p>}
      {currentQuote?.amount && <p className="info-box full" role="status"><strong>Bill total {money.format(Number(currentQuote.amount))}</strong></p>}
      {pending && !busy && <p className="info-box full" role="status">{recovery.store ? "The previous response was not confirmed. Retry the original bill before recording another delivery." : pendingPostingMessage}</p>}
      <div className="modal-actions full">
        <button type="button" className="button secondary" disabled={busy || pending} onClick={() => { setEditing(false); setEntries({}); }}>Cancel receipt</button>
        <button type="submit" className="button primary" disabled={busy || !writable || (!pending && (!canQuote || !currentQuote?.amount || Number(currentQuote.amount) <= 0))}>
          {busy ? "Posting bill…" : pending ? "Retry bill" : "Post purchase bill"}
        </button>
      </div>
    </form>}
    {!!snapshot?.receipts.length && <div className="purchase-receiving-history">
      <h4>Received bills</h4>
      {snapshot.receipts.map(row => <button type="button" className="detail-trail-row" key={row.id} disabled={busy || pending} onClick={() => onOpen(row)}>
        <PackageCheck size={17} aria-hidden="true" /><span><strong>{row.number}</strong><small>{row.date}{row.cancelled ? " · Cancelled" : ""}</small></span><strong>{money.format(Number(row.amount))}</strong>
      </button>)}
    </div>}
  </section>;
}
