import { lineDiscountMode } from "./lineDiscount.js";
import React, { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";

export function useDocumentPreview({
  api,
  companyId,
  kind,
  form,
  lines,
  enabled,
  recordId,
}) {
  const [result, setResult] = useState(null);
  const payload = {
    kind,
    name: "Preview",
    date: form.date,
    data: {
      lines,
      applied_to: form.applied_to,
      preview_record_id: ["credit_note", "debit_note"].includes(kind) ? recordId : undefined,
      place_of_supply: form.place_of_supply,
      supplier_state: form.supplier_state,
      party_gstin: form.party_gstin,
      document_discount_percent: form.document_discount_percent,
      round_total: form.round_total,
    },
  };
  const key = JSON.stringify([companyId, payload]);
  const valid =
    enabled &&
    lines.length > 0 &&
    lines.every((l) => l.description.trim() && l.rate !== "");
  useEffect(() => {
    if (!valid) return;
    let active = true;
    const timer = setTimeout(
      () =>
        api(`/companies/${companyId}/documents/preview`, {
          method: "POST",
          body: JSON.stringify(payload),
        })
          .then((value) => {
            if (active) setResult({ key, value });
          })
          .catch((error) => {
            if (active) setResult({ key, value: { error: error.message } });
          }),
      300,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [api, key, valid]);
  return valid && result?.key === key ? result.value : null;
}

export function DocumentIdentity({
  form,
  setForm,
  change,
  kind,
  purchase,
  showTax,
  company,
  targets,
  onSelectSource,
}) {
  const update = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }));
  return (
    <section className="document-identity full">
      <div className="editor-section-heading">
        <span>01</span>
        <div>
          <h3>
            {purchase
              ? "Supplier & bill details"
              : "Customer & document details"}
          </h3>
          <p>Choose an existing party to fill its saved details.</p>
        </div>
      </div>
      {["credit_note", "debit_note"].includes(kind) && (
        <label className="source-document">
          Original posted document
          <select
            className="form-select"
            required
            value={form.applied_to}
            onChange={(e) => onSelectSource(e.target.value)}
          >
            <option value="">Choose the invoice, POS receipt or bill</option>
            {targets.map((r) => (
              <option key={r.id} value={r.id}>
                {r.number} · {r.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="document-header-grid">
        <div className="document-customer">
          <label>
            {purchase ? "Supplier / description" : "Customer / description"}
            <input
              autoComplete="off"
              name="name"
              list="apex-party-options"
              required
              value={form.name}
              onChange={change}
              placeholder="Search or enter party name"
            />
          </label>
          <div className="customer-inline">
            <label>
              Phone
              <input
                value={form.party_phone}
                maxLength={32}
                onChange={(e) => update("party_phone", e.target.value)}
                placeholder="Phone number"
              />
            </label>
            {showTax && (
              <label>
                GSTIN
                <input
                  name="party_gstin"
                  value={form.party_gstin}
                  maxLength={15}
                  onChange={change}
                  placeholder="If registered"
                />
              </label>
            )}
          </div>
          <details className="address-details">
            <summary>
              Billing & shipping addresses
              {form.party_address ? " · saved details filled" : ""}
            </summary>
            <div className="form-grid">
              <label>
                Billing address
                <textarea
                  name="party_address"
                  maxLength={1000}
                  value={form.party_address}
                  onChange={change}
                />
              </label>
              <label>
                Shipping address
                <textarea
                  maxLength={1000}
                  value={form.shipping_address}
                  onChange={(e) => update("shipping_address", e.target.value)}
                />
              </label>
            </div>
          </details>
        </div>
        <div className="document-meta">
          <label>
            Reference number
            <input
              name="number"
              maxLength={16}
              value={form.number}
              onChange={change}
              placeholder="Assigned on save"
            />
          </label>
          <label>
            Document date
            <input
              required
              type="date"
              name="date"
              value={form.date}
              onInput={change}
              onChange={change}
            />
          </label>
          {["sales_invoice", "purchase_bill"].includes(kind) && (
            <label>
              Due date
              <input
                type="date"
                name="due_date"
                min={form.date}
                value={form.due_date}
                onInput={change}
                onChange={change}
              />
            </label>
          )}
          {showTax && (
            <label>
              Place of supply · state code
              <input
                name="place_of_supply"
                required={company.tax_mode === "regular"}
                pattern="[0-9]{2}"
                value={form.place_of_supply}
                onChange={change}
              />
            </label>
          )}
          {purchase && (
            <label>
              Supplier state code
              <input
                required={company.tax_mode === "regular"}
                pattern="[0-9]{2}"
                value={form.supplier_state}
                onChange={(e) => update("supplier_state", e.target.value)}
              />
            </label>
          )}
        </div>
      </div>
    </section>
  );
}

export function DocumentItems({
  onPriceHistory,
  lines,
  setLines,
  changeLine,
  emptyLine,
  showTax,
  purchase,
  company,
  preview,
  money,
}) {
  return (
    <section
      className={`document-items full ${showTax ? "with-tax" : "without-tax"}`}
    >
      <div className="editor-section-heading">
        <span>02</span>
        <div>
          <h3>Items & services</h3>
          <p>
            Select an item or type a description. Tax and totals are calculated
            automatically.
          </p>
        </div>
        <small>
          {lines.length} {lines.length === 1 ? "line" : "lines"}
        </small>
      </div>
      <div className="document-grid-head" aria-hidden="true">
        <span>ITEM / SERVICE</span>
        <span>QTY / UNIT</span>
        <span>RATE ₹</span>
        <span>DISCOUNT</span>
        {showTax && <span>GST %</span>}
        <span>AMOUNT</span>
        <span />
      </div>
      {lines.map((line, index) => {
        const calculated = preview?.data?.lines?.[index];
        return (
          <div
            className={`document-item-row ${showTax ? "with-tax" : "without-tax"}`}
            key={index}
          >
            <label className="item-description">
              <span className="mobile-field-label">
                Item / service {index + 1}
              </span>
              <input
                name="description"
                list="apex-item-options"
                required
                maxLength={200}
                aria-label={`Item ${index + 1} description`}
                value={line.description}
                onChange={(e) => changeLine(index, e)}
                placeholder="Search item or enter description"
              />
              <small>
                #{index + 1}
                {line.item_id ? " · linked to item" : " · custom line"}
                {line.item_id && onPriceHistory && <button type="button" className="button secondary price-history-trigger" onClick={() => onPriceHistory(index)}>Previous prices</button>}
              </small>
            </label>
            <label>
              <span className="mobile-field-label">Quantity</span>
              <input
                name="quantity"
                type="number"
                min="0.001"
                step="any"
                required
                aria-label={`Item ${index + 1} quantity`}
                value={line.quantity}
                onChange={(e) => changeLine(index, e)}
              />
              <input
                className="line-unit"
                name="unit"
                maxLength={24}
                aria-label={`Item ${index + 1} unit`}
                value={line.unit || ""}
                onChange={(e) => changeLine(index, e)}
                placeholder="Unit"
              />
            </label>
            <label>
              <span className="mobile-field-label">Rate ₹</span>
              <input
                name="rate"
                type="number"
                min="0"
                step="0.01"
                required
                aria-label={`Item ${index + 1} rate`}
                value={line.rate}
                onChange={(e) => changeLine(index, e)}
              />
            </label>
            <label>
              <span className="mobile-field-label">Line discount</span>
              <select name="discount_mode" aria-label={`Item ${index + 1} discount mode`} value={lineDiscountMode(line)} onChange={e => changeLine(index, e)} style={{ minHeight: 44 }}>
                <option value="percent">Discount %</option><option value="amount">Discount ₹</option>
              </select>
              <input
                name={lineDiscountMode(line) === "amount" ? "discount_amount" : "discount_percent"}
                type="number"
                min="0"
                max={lineDiscountMode(line) === "amount" ? undefined : "100"}
                step="0.01"
                aria-label={`Item ${index + 1} discount ${lineDiscountMode(line) === "amount" ? "amount" : "percent"}`}
                value={lineDiscountMode(line) === "amount" ? line.discount_amount ?? "0" : line.discount_percent ?? "0"}
                onChange={(e) => changeLine(index, e)}
                style={{ minHeight: 44 }}
              />
            </label>
            {showTax && (
              <label>
                <span className="mobile-field-label">GST %</span>
                <input
                  name="gst_rate"
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  required
                  disabled={
                    company.tax_mode === "regular" &&
                    line.tax_treatment !== "taxable"
                  }
                  aria-label={`Item ${index + 1} GST rate`}
                  value={line.gst_rate}
                  onChange={(e) => changeLine(index, e)}
                />
              </label>
            )}
            <output
              className="line-amount"
              aria-label={`Item ${index + 1} amount`}
            >
              {calculated
                ? money(Number(calculated.taxable) + Number(calculated.tax))
                : "—"}
            </output>
            <button
              type="button"
              className="icon-button line-remove"
              aria-label={`Remove item ${index + 1}`}
              disabled={lines.length === 1}
              onClick={() => setLines(lines.filter((_, i) => i !== index))}
            >
              <Trash2 size={16} />
            </button>
            <details className="line-more">
              <summary>
                HSN, MRP{showTax ? " & tax options" : " & details"}
              </summary>
              <div className="line-options-grid">
                <label>
                  HSN / SAC
                  <input
                    name="hsn"
                    maxLength={16}
                    value={line.hsn}
                    onChange={(e) => changeLine(index, e)}
                    placeholder="Code"
                  />
                </label>
                <label>
                  MRP · reference only
                  <input
                    name="mrp"
                    type="number"
                    min="0"
                    step="0.01"
                    value={line.mrp || ""}
                    onChange={(e) => changeLine(index, e)}
                  />
                </label>
                {showTax && (
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={!!line.price_includes_tax}
                      onChange={(e) =>
                        setLines(
                          lines.map((row, i) =>
                            i === index
                              ? { ...row, price_includes_tax: e.target.checked }
                              : row,
                          ),
                        )
                      }
                    />
                    Rate includes GST
                  </label>
                )}
                {company.tax_mode === "regular" && (
                  <label>
                    GST treatment
                    <select
                      className="form-select"
                      name="tax_treatment"
                      value={line.tax_treatment || "taxable"}
                      onChange={(e) => changeLine(index, e)}
                    >
                      <option value="taxable">Taxable</option>
                      <option value="nil_rated">Nil rated</option>
                      <option value="exempt">Exempt</option>
                      <option value="non_gst">Non-GST supply</option>
                    </select>
                  </label>
                )}
                {purchase && company.tax_mode === "regular" && (
                  <label>
                    Supplier GST treatment
                    <select
                      className="form-select"
                      name="itc_treatment"
                      value={line.itc_treatment || "pending_review"}
                      onChange={(e) => changeLine(index, e)}
                    >
                      <option value="pending_review">
                        Input credit pending review
                      </option>
                      <option value="ineligible">
                        Ineligible · include GST in cost
                      </option>
                    </select>
                  </label>
                )}
              </div>
            </details>
          </div>
        );
      })}
      <button
        type="button"
        className="button secondary add-document-line"
        disabled={lines.length >= 100}
        onClick={() => setLines([...lines, emptyLine()])}
      >
        <Plus size={16} />
        Add item / service
      </button>
    </section>
  );
}

export function DocumentTotals({ preview, money }) {
  if (!preview)
    return (
      <div className="document-totals" role="status">
        <small>DOCUMENT TOTAL</small>
        <strong>—</strong>
        <p>Complete the item details to calculate totals.</p>
      </div>
    );
  if (preview.error)
    return (
      <div className="error document-totals" role="status">
        {preview.error}
      </div>
    );
  const data = preview.data;
  return (
    <div className="document-totals" role="status">
      <div>
        <span>Subtotal after discounts</span>
        <b>{money(data.taxable)}</b>
      </div>
      {["cgst", "sgst", "igst", "supplier_tax"]
        .filter((k) => Number(data[k]))
        .map((k) => (
          <div key={k}>
            <span>
              {k === "supplier_tax" ? "Supplier tax" : k.toUpperCase()}
            </span>
            <b>{money(data[k])}</b>
          </div>
        ))}
      {Number(data.round_off) !== 0 && (
        <div>
          <span>Round off</span>
          <b>{money(data.round_off)}</b>
        </div>
      )}
      <div className="document-grand-total">
        <span>Total</span>
        <strong>{money(preview.amount)}</strong>
      </div>
    </div>
  );
}
