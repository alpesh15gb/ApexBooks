import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { X } from "lucide-react";
import { businessDate } from "./businessDate.js";
import { usePostingRequest } from "./usePostingRequest.js";
import { registerPostingRequest } from "./postingRegistry.js";

const money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });

export default function PosReturn({ company, sale, banks, api, recoveryStore, recovered, onClose, onComplete }) {
  const settlementId = useId();
  const bankId = useId();
  const [source, setSource] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [loadAttempt, reload] = useState(0);
  const [quantities, setQuantities] = useState({});
  const [restock, setRestock] = useState(true);
  const [method, setMethod] = useState("");
  const [bank, setBank] = useState("");
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [quote, setQuote] = useState(null);
  const [error, setError] = useState("");
  const posting = usePostingRequest({ definitiveRetryStatuses: [409], definitiveRetryCodes: ["POS_REQUOTE_REQUIRED"] });
  const { busy } = posting;
  const operation = useRef(recovered);
  const pending = !!operation.current || posting.pending;
  const writable = ["owner", "editor"].includes(company.role);
  const locked = busy || pending || !writable;
  const path = `/companies/${company.id}/pos/${sale.id}/return`;
  const lines = source?.return_capacity_lines;
  const selectedBank = banks.find(row => row.id === bank) || (banks.length === 1 ? banks[0] : null);
  useEffect(() => registerPostingRequest({ get pending() { return !!operation.current; } }), []);

  useEffect(() => {
    const controller = new AbortController();
    api(`/companies/${company.id}/records/${sale.id}`, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) {
        setSource(value);
        setLoadError("");
      }
    }).catch(failure => {
      if (!controller.signal.aborted) setLoadError(failure.message);
    });
    return () => controller.abort();
  }, [api, company.id, sale.id, loadAttempt]);

  const selected = useMemo(() => (lines || []).flatMap((line, index) => {
    const value = quantities[index];
    return value && Number(value) > 0 ? [{ source_index: index, quantity: value }] : [];
  }), [lines, quantities]);
  const invalidQuantity = selected.some(({ source_index, quantity }) => {
    const maximum = lines[source_index].remaining_return_quantity;
    return maximum === null || Number(quantity) > Number(maximum) || !/^\d+(?:\.\d{1,3})?$/.test(quantity);
  });
  const payload = useMemo(() => ({
    date: businessDate(),
    lines: selected,
    source_version: source?.data?.version ?? 0,
    return_stock: restock,
    payment_account: method || null,
    ...(method === "bank" && selectedBank ? { bank_account_id: selectedBank.id } : {}),
    reason: reason.trim(),
  }), [source, selected, restock, method, selectedBank, reason]);
  const valid = !!source?.posted && !source.cancelled && selected.length > 0 && !invalidQuantity &&
    (method !== "bank" || !!selectedBank);
  const currentQuote = quote?.payload === payload ? quote : null;
  const amount = currentQuote?.result?.amount;
  const paymentApproved = confirmed === payload;

  useEffect(() => {
    if (!valid || pending) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api(`${path}/preview`, { method: "POST", signal: controller.signal, body: JSON.stringify(payload) })
        .then(result => { if (!controller.signal.aborted) setQuote({ payload, result }); })
        .catch(failure => { if (!controller.signal.aborted) setQuote({ payload, error: failure.message }); });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [api, path, payload, pending, valid]);

  async function submit(event) {
    event?.preventDefault();
    const retrying = !!operation.current;
    if (!writable || busy || (!retrying && (!valid || !amount || (method && !paymentApproved)))) return;
    setError("");
    try {
      if (!retrying) {
        const request = { key: crypto.randomUUID(), saleId: sale.id, body: JSON.stringify({ ...payload, expected_total: amount }) };
        recoveryStore?.save(request);
        operation.current = request;
      }
      const request = operation.current;
      const result = await posting.run(() => api(path, {
        method: "POST",
        headers: { "Idempotency-Key": request.key },
        body: request.body,
      }));
      if (result) {
        recoveryStore?.clear(request.key);
        operation.current = null;
        onComplete(result.value);
      }
    } catch (failure) {
      // Every return rejection before commit is definitive (committed keys replay first), except timeouts.
      if (operation.current && !posting.isPending() && failure.status >= 400 && failure.status < 500 && failure.status !== 408) {
        recoveryStore?.clear(operation.current.key);
        operation.current = null;
        setConfirmed(false);
        if (failure.code === "POS_REQUOTE_REQUIRED") {
          if (recovered) { onClose(failure.message); return; }
          setQuantities({});
          reload(value => value + 1);
        }
      }
      setError(failure.message);
    }
  }

  return <div className="overlay" onMouseDown={event => {
    if (event.target === event.currentTarget && !busy && !pending) onClose();
  }}>
    <section className="modal" role="dialog" aria-modal="true" aria-labelledby="pos-return-title">
      <div className="modal-heading">
        <div><h2 id="pos-return-title">Return {sale.number}</h2><p>{sale.name}</p></div>
        <button type="button" className="icon-button" aria-label="Close return" disabled={busy || pending} onClick={() => onClose()}><X size={18} /></button>
      </div>
      {recovered && <>
        <p className="info-box" role="status">The previous return response was not confirmed. Retry the original request before sending another refund.</p>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="button" className="button primary" onClick={() => submit()} disabled={!writable || busy}>{busy ? "Recovering return…" : "Retry return"}</button>
      </>}
      {!source && !recovered && <p role={loadError ? "alert" : "status"}>{loadError || "Checking quantities still eligible for return…"}</p>}
      {loadError && <button type="button" className="button secondary" onClick={() => { setLoadError(""); reload(value => value + 1); }}>Retry loading receipt</button>}
      {source && !recovered && <form className="form-grid" onSubmit={submit}>
        <fieldset className="form-grid full submission-fields" disabled={locked}>
          <legend>Return items</legend>
          {lines?.map((line, index) => <label className="full" key={index}>
            {line.description} · {line.remaining_return_quantity === null ? "Quantity needs review" : `${line.remaining_return_quantity} ${line.unit || "units"} remaining`}
            <input aria-label={`Return quantity for ${line.description} (line ${index + 1})`} type="number"
              min="0" max={line.remaining_return_quantity ?? "0"} step="0.001"
              value={quantities[index] || ""} disabled={Number(line.remaining_return_quantity) <= 0}
              onChange={event => setQuantities(current => ({ ...current, [index]: event.target.value }))} />
            {line.return_capacity_reason && <small>{line.return_capacity_reason}</small>}
          </label>)}
          {!lines?.some(line => Number(line.remaining_return_quantity) > 0) && <p className="full">No items have a confirmed returnable quantity.</p>}
          <label className="checkbox-label full"><input type="checkbox" checked={restock} onChange={event => setRestock(event.target.checked)} />Return resellable items to inventory</label>
          <label className="full">Reason <input value={reason} onChange={event => setReason(event.target.value)} maxLength={200} /></label>
          <div className="full">
            <label htmlFor={settlementId}>Settlement</label>
            <select id={settlementId} className="form-select" value={method} onChange={event => setMethod(event.target.value)}>
              <option value="">Keep as customer credit</option>
              <option value="cash">Cash refund</option>
              <option value="bank">Bank / UPI / card refund</option>
            </select>
          </div>
          {method === "bank" && <div className="full">
            <label htmlFor={bankId}>Refund bank account</label>
            <select id={bankId} className="form-select" value={selectedBank?.id || ""} onChange={event => setBank(event.target.value)} required>
              {!selectedBank && <option value="">Choose a bank account</option>}
              {banks.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
            </select>
          </div>}
          {invalidQuantity && <p className="error full" role="alert">Enter a quantity within the remaining amount shown for each item.</p>}
          {currentQuote?.error && <p className="error full" role="alert">{currentQuote.error}</p>}
          {valid && !currentQuote && <p className="full" role="status">Checking return total…</p>}
          {amount && <p className="info-box full" role="status"><strong>Return total {money.format(Number(amount))}</strong></p>}
          {method && amount && <label className="checkbox-label full">
            <input type="checkbox" checked={paymentApproved} onChange={event => setConfirmed(event.target.checked ? payload : false)} />
            {method === "bank" ? "I confirmed this refund in the bank, UPI or card terminal." : "I am recording the cash paid out for this return."}
          </label>}
        </fieldset>
        {pending && !busy && <p role="status" className="info-box full">The previous return response was not confirmed. Retry the original request before sending another refund.</p>}
        {error && <p className="error full" role="alert">{error}</p>}
        <div className="modal-actions full">
          <button type="button" className="button secondary" disabled={busy || pending} onClick={() => onClose()}>Cancel</button>
          <button type="submit" className="button primary" disabled={busy || !writable || (!pending && (!valid || !amount || (method && !paymentApproved)))}>
            {busy ? "Posting return…" : pending ? "Retry return" : "Post return"}
          </button>
        </div>
      </form>}
    </section>
  </div>;
}
