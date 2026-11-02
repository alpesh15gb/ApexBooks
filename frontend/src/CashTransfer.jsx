import { businessDate } from "./businessDate.js";
import { usePostingRequest, pendingPostingMessage } from "./usePostingRequest.js";
import React, { useEffect, useState } from "react";
import { Plus, X } from "lucide-react";

export default function CashTransfer({ companyId, onSaved, role, banks = [], preferredBankId="default" }) {
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(businessDate());
  const [name, setName] = useState("Cash deposit");
  const [amount, setAmount] = useState("");
  const [direction, setDirection] = useState("cash_to_bank");
  const [bankAccountId, setBankAccountId] = useState("default");
  const [toBankId, setToBankId] = useState("default");
  const [error, setError] = useState("");
  const posting = usePostingRequest();
  const { busy, pending } = posting;
  const requestClose = () => { if (!busy && !pending) setOpen(false); };
  const [submissionKey, setSubmissionKey] = useState(() => crypto.randomUUID());
  useEffect(() => {
    setOpen(false);
    setError("");
    setAmount("");
    setBankAccountId("default");
  }, [companyId]);
  useEffect(()=>{if(direction==="bank_to_bank"&&(toBankId===bankAccountId||!banks.some(bank=>bank.id===toBankId)))setToBankId(banks.find(bank=>bank.id!==bankAccountId)?.id||"")},[direction,toBankId,bankAccountId,banks]);
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setError("");
    try {
      const path = `/api/companies/${companyId}/records`;
      const options = {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.token}`,
          "Idempotency-Key": submissionKey,
        },
        body: JSON.stringify({
          kind: "bank_transfer",
          name,
          date,
          amount,
          data: {
            direction,
            bank_account_id: bankAccountId,
            to_bank_account_id: toBankId,
          },
        }),
      };
      if (!await posting.run(async () => {
      const response = await fetch(path, options);
      const data = await response.json();
      if (!response.ok)
        throw Object.assign(new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Could not record transfer",
        ), { status: response.status });
      })) return;
      setOpen(false);
      setAmount("");
      onSaved();
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <>
      <button
        className="button secondary cash-transfer-button"
        disabled={busy || pending || !companyId || !["owner", "editor"].includes(role)}
        onClick={() => {
          setSubmissionKey(crypto.randomUUID());
          setBankAccountId(preferredBankId);
          setOpen(true);
        }}
      >
        <Plus size={16} /> Record cash/bank transfer
      </button>
      {open && (
        <div
          className="overlay"
          onMouseDown={(event) =>
            event.target === event.currentTarget && requestClose()
          }
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Entry form"
          >
            <div className="modal-heading">
              <div>
                <h2>Cash and bank transfer</h2>
                <p>
                  Record cash deposits, withdrawals or transfers between bank
                  accounts.
                </p>
              </div>
              <button
                className="icon-button"
                aria-label="Close"
                onClick={requestClose}
                  disabled={busy || pending}
              >
                <X size={18} />
              </button>
            </div>
            <form className="form-grid" onSubmit={submit}>
              <fieldset className="form-grid full submission-fields" disabled={busy || pending}>
              <label className="full">
                Direction
                <select
                  className="form-select"
                  value={direction}
                  onChange={(event) => {
                    setDirection(event.target.value);
                    if (
                      event.target.value === "bank_to_bank" &&
                      toBankId === bankAccountId
                    )
                      setToBankId(
                        banks.find((bank) => bank.id !== bankAccountId)?.id ||
                          "",
                      );
                    setName(
                      event.target.value === "cash_to_bank"
                        ? "Cash deposit"
                        : event.target.value === "bank_to_bank"
                          ? "Bank transfer"
                          : "Cash withdrawal",
                    );
                  }}
                >
                  <option value="cash_to_bank">Cash to bank</option>
                  <option value="bank_to_cash">Bank to cash</option>
                  <option value="bank_to_bank">Bank to bank</option>
                </select>
              </label>
              <label className="full">
                Bank account
                <select
                  className="form-select"
                  value={bankAccountId}
                  onChange={(event) => setBankAccountId(event.target.value)}
                >
                  {banks.map((bank) => (
                    <option value={bank.id} key={bank.id}>
                      {bank.name}
                    </option>
                  ))}
                </select>
              </label>
              {direction === "bank_to_bank" && (
                <label className="full">
                  Destination bank account
                  <select
                    className="form-select"
                    aria-label="Destination bank account"
                    value={toBankId}
                    onChange={(event) => setToBankId(event.target.value)}
                  >
                    {banks
                      .filter((bank) => bank.id !== bankAccountId)
                      .map((bank) => (
                        <option key={bank.id} value={bank.id}>
                          {bank.name}
                        </option>
                      ))}
                  </select>
                </label>
              )}
              <label className="full">
                Description
                <input
                  required
                  maxLength="120"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <label>
                Date
                <input
                  type="date"
                  required
                  value={date}
                  onChange={(event) => setDate(event.target.value)}
                />
              </label>
              <label>
                Amount (₹)
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  required
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                />
              </label>
              </fieldset>
              {pending && !busy && <p className="info-box full" role="status">{pendingPostingMessage}</p>}
              {error && <div className="error full">{error}</div>}
              <div className="modal-actions full">
                <button
                  type="button"
                  className="button secondary"
                  onClick={requestClose}
                  disabled={busy || pending}
                >
                  Cancel
                </button>
                <button className="button primary" disabled={busy}>
                  {busy ? "Saving…" : "Record transfer"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
