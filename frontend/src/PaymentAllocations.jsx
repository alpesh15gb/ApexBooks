import React from "react";

const currency = (value) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(
    value || 0,
  );

export default function PaymentAllocations({
  rows,
  setRows,
  targets,
  party,
  onParty,
  paymentAmount,
  advance,
  onAdvance,
  allowAdvance,
  onPaymentAmount,
}) {
  const selected = new Set(rows.map((row) => row.document_id).filter(Boolean));
  const total =
    rows.reduce(
      (sum, row) => sum + Math.round(Number(row.amount || 0) * 100),
      0,
    ) / 100;
  function update(index, changes) {
    setRows(rows.map((row, i) => (i === index ? { ...row, ...changes } : row)));
  }
  return (
    <div className="full line-card">
      {allowAdvance && (
        <label>
          <input
            type="checkbox"
            checked={advance}
            onChange={(event) => onAdvance(event.target.checked)}
          />{" "}
          Record as an advance for later allocation
        </label>
      )}
      {advance ? (
        <p>
          This payment will remain in the advance account until you apply it to
          an invoice or bill.
        </p>
      ) : (
        <>
          <div className="line-heading">
            <strong>Apply payment to documents</strong>
            <span>
              {currency(total)} allocated of {currency(Number(paymentAmount))}
            </span>
          </div>
          {rows.map((row, index) => (
            <div className="form-grid allocation-row" key={index}>
              <label>
                Invoice or bill
                <select
                  className="form-select"
                  required
                  value={row.document_id}
                  onChange={(event) => {
                    const target = targets.find(
                      (item) => item.id === event.target.value,
                    );
                    const partyChanged =
                      index === 0 &&
                      target?.name?.trim().toLowerCase() !==
                        party.trim().toLowerCase();
                    const others = partyChanged
                      ? 0
                      : rows.reduce(
                          (sum, value, i) =>
                            i === index
                              ? sum
                              : sum +
                                Math.round(Number(value.amount || 0) * 100),
                          0,
                        );
                    const available = Math.round(
                      Number(target?.outstanding || 0) * 100,
                    );
                    const budget =
                      paymentAmount === ""
                        ? available
                        : Math.max(
                            0,
                            Math.round(Number(paymentAmount || 0) * 100) -
                              others,
                          );
                    const amount = target
                      ? (Math.min(available, budget) / 100).toFixed(2)
                      : "";
                    if (index === 0) {
                      onParty(target?.name || "");
                      if (target && paymentAmount === "")
                        onPaymentAmount?.(String(target.outstanding));
                      if (partyChanged) {
                        setRows([{ document_id: event.target.value, amount }]);
                        return;
                      }
                    }
                    update(index, { document_id: event.target.value, amount });
                  }}
                >
                  <option value="">Choose document</option>
                  {targets
                    .filter(
                      (item) =>
                        (!party ||
                          index === 0 ||
                          item.name.trim().toLowerCase() ===
                            party.trim().toLowerCase()) &&
                        (!selected.has(item.id) || item.id === row.document_id),
                    )
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.number || item.id} · {item.name} ·{" "}
                        {currency(Number(item.outstanding))} due
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Allocated amount (₹)
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  max={
                    targets.find((item) => item.id === row.document_id)
                      ?.outstanding || undefined
                  }
                  required
                  value={row.amount}
                  onChange={(event) =>
                    update(index, { amount: event.target.value })
                  }
                />
              </label>
              {index > 0 && (
                <button
                  type="button"
                  className="link full"
                  onClick={() => setRows(rows.filter((_, i) => i !== index))}
                >
                  Remove document
                </button>
              )}
            </div>
          ))}
          {paymentAmount !== "" &&
            Math.round(total * 100) !==
              Math.round(Number(paymentAmount || 0) * 100) && (
              <p
                className={
                  total > Number(paymentAmount) ? "error" : "allocation-hint"
                }
                role="status"
              >
                {total > Number(paymentAmount)
                  ? `Allocation exceeds the payment by ${currency(total - Number(paymentAmount))}. Reduce the allocated amounts.`
                  : `${currency(Number(paymentAmount) - total)} remaining to allocate.`}
              </p>
            )}
          <button
            type="button"
            className="button secondary"
            disabled={!rows[0]?.document_id || rows.length >= 100}
            onClick={() => setRows([...rows, { document_id: "", amount: "" }])}
          >
            Add another document
          </button>
        </>
      )}
    </div>
  );
}
