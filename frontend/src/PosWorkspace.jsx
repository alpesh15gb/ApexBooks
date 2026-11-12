import { businessDate } from "./businessDate.js";
import { isActiveMaster } from "./masterLifecycle.js";
import { usePostingRequest, pendingPostingMessage } from "./usePostingRequest.js";
import React, { useEffect, useMemo, useState } from "react";
import { Plus, Minus, Trash2, Search, ReceiptIndianRupee } from "lucide-react";
const money = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(
    Number(n || 0),
  );
const today = () => businessDate();
export default function PosWorkspace({
  company,
  records,
  api,
  refresh,
  onPdf,
}) {
  const [search, setSearch] = useState(""),
    [cart, setCart] = useState([]),
    [customer, setCustomer] = useState("Walk-in customer"),
    [method, setMethod] = useState("cash"),
    [bank, setBank] = useState("default"),
    [banks, setBanks] = useState([]),
    [tender, setTender] = useState(""),
    [inclusive, setInclusive] = useState(false),
    [round, setRound] = useState(false),
    [preview, setPreview] = useState(null),
    [error, setError] = useState(""),
    [key, setKey] = useState(() => crypto.randomUUID()),
    [receipt, setReceipt] = useState(null);
  const posting = usePostingRequest();
  const { busy, pending } = posting;
  const [billing,setBilling]=useState({address:"",gstin:"",phone:"",place:company.state_code});
  const items = records.filter((r) => r.kind === "item" && isActiveMaster(r)),
    filtered = items
      .filter((r) =>
        `${r.name} ${r.data?.hsn || ""} ${r.data?.barcode || ""}`
          .toLowerCase()
          .includes(search.toLowerCase()),
      )
      .slice(0, 30);
  const lines = useMemo(
    () =>
      cart.map((row) => ({
        item_id: row.item.id,
        description: row.item.name,
        hsn: row.item.data?.hsn || "",
        unit: row.item.data?.unit || "",
        quantity: row.quantity,
        rate: row.rate,
        discount_percent: row.discount,
        price_includes_tax: inclusive,
        gst_rate:
          company.tax_mode === "regular" ? row.item.data?.gst_rate || "0" : "0",
        tax_treatment:
          company.tax_mode === "regular" &&
          Number(row.item.data?.gst_rate || 0) === 0
            ? (row.item.data?.tax_treatment && row.item.data.tax_treatment!=="taxable" ? row.item.data.tax_treatment : "nil_rated")
            : "taxable",
      })),
    [cart, inclusive, company.tax_mode],
  );
  useEffect(() => {
    let live = true;
    api(`/companies/${company.id}/bank-accounts`)
      .then((r) => {
        if (live) setBanks(r);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [company.id, api]);
  useEffect(() => {
    let live = true;
    setPreview(null);
    if (!lines.length) return;
    const timer = setTimeout(() => {
      api(`/companies/${company.id}/documents/preview`, {
        method: "POST",
        body: JSON.stringify({
          kind: "pos",
          name: customer,
          data: {
            lines,
            place_of_supply: billing.place,party_address:billing.address,party_gstin:billing.gstin,party_phone:billing.phone,
            round_total: round,
          },
        }),
      })
        .then((r) => {
          if (live) {
            setPreview(r);
            setError("");
          }
        })
        .catch((e) => {
          if (live) setError(e.message);
        });
    }, 200);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [lines, round, company.id, company.state_code, api, customer,billing]);
  function add(item) {
    if (busy || pending) return;
    setCart((current) => {
      const found = current.find((row) => row.item.id === item.id);
      return found
        ? current.map((row) =>
            row.item.id === item.id
              ? { ...row, quantity: String(Number(row.quantity) + 1) }
              : row,
          )
        : [
            ...current,
            {
              item,
              quantity: "1",
              rate: String(item.data?.sale_rate || "0"),
              discount: "0",
            },
          ];
    });
    setSearch("");
    setReceipt(null);
  }
  function update(id, field, value) {
    setCart(
      cart.map((row) =>
        row.item.id === id ? { ...row, [field]: value } : row,
      ),
    );
  }
  const change =
    method === "cash" && tender !== ""
      ? Math.round((Number(tender) - Number(preview?.amount || 0)) * 100) / 100
      : 0;
  async function checkout(e) {
    e.preventDefault();
    if (busy || !preview || !["owner", "editor"].includes(company.role)) return;
    setError("");
    try {
      const path = `/companies/${company.id}/records`;
      const options = {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify({
          kind: "pos",
          name: customer.trim() || "Walk-in customer",
          date: today(),
          data: {
            lines,
            place_of_supply: billing.place,party_address:billing.address,party_gstin:billing.gstin,party_phone:billing.phone,
            round_total: round,
            payment_account: method,
            bank_account_id: bank,
            tender_amount:
              method === "cash" ? tender || preview.amount : preview.amount,
          },
        }),
      };
      const result = await posting.run(() => api(path, options));
      if (!result) return;
      setReceipt(result.value);
      setCart([]);
      setTender("");
      setCustomer("Walk-in customer");
      setBilling({address:"",gstin:"",phone:"",place:company.state_code});
      setKey(crypto.randomUUID());
      await refresh();
    } catch (e) {
      setError(e.message);
    }
  }
  const daySales = records.filter(
    (r) => r.kind === "pos" && r.posted && !r.cancelled && r.date === today(),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow green">SALES COUNTER</div>
          <h1>Point of sale</h1>
          <p>
            {daySales.length} sales today ·{" "}
            {money(daySales.reduce((total, r) => total + Number(r.amount), 0))}
          </p>
        </div>
      </div>
      {receipt && (
        <div className="info-box pos-receipt" role="status">
          <strong>
            {receipt.number} · Sale completed · {money(receipt.amount)}
          </strong>
          <button className="button secondary" onClick={() => onPdf(receipt)}>
            <ReceiptIndianRupee size={16} />
            Download receipt
          </button>
        </div>
      )}
      {error && (
        <div className="error banner" role="alert">
          {error}
        </div>
      )}
      <div className="pos-grid">
        <section className="panel settings-panel">
          <h2>Products and services</h2>
          <label className="search">
            <Search size={16} />
            <input
              aria-label="Search POS items or scan barcode"
              disabled={busy || pending}
              placeholder="Search name, HSN or scan barcode"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  const exact = items.find(
                    (r) =>
                      (r.data?.barcode && r.data.barcode === search) ||
                      r.name.toLowerCase() === search.toLowerCase(),
                  );
                  // Clear after adding so the next barcode scan starts fresh.
                  if (exact || filtered.length === 1) { add(exact || filtered[0]); setSearch(""); }
                }
              }}
            />
          </label>
          <div className="pos-products">
            {filtered.map((item) => (
              <button
                className="pos-product"
                key={item.id}
                onClick={() => add(item)}
                disabled={busy || pending}
              >
                {item.data?.image_thumbnail&&<img src={item.data.image_thumbnail} alt={item.name} loading="lazy"/>}
              <strong>{item.name}</strong>
                <span>
                  {money(item.data?.sale_rate)}
                  {item.data?.unit && ` / ${item.data.unit}`}
                </span>
                <small>
                  {item.data?.barcode || item.data?.hsn || "Add to cart"}
                </small>
                <Plus size={17} />
              </button>
            ))}
          </div>
          {!items.length && <p>Add items in Items to start selling.</p>}
          {!!items.length && !filtered.length && <p>No matching items.</p>}
        </section>
        <section className="panel settings-panel">
          <h2>Current sale</h2>
          <form className="form-grid" onSubmit={checkout}>
            <fieldset className="form-grid full submission-fields" disabled={busy || pending}>
            <label className="full">
              Customer
              <input
                list="pos-parties"
                required
                value={customer}
                onChange={(e) => {const value=e.target.value;setCustomer(value);const party=records.find(r=>r.kind==="party"&&r.name.toLowerCase()===value.trim().toLowerCase());setBilling({address:party?.data?.address||"",gstin:party?.data?.gstin||"",phone:party?.data?.phone||"",place:company.state_code})}}
              />
              <datalist id="pos-parties">
                {records
                  .filter((r) => r.kind === "party" && isActiveMaster(r))
                  .map((r) => (
                    <option key={r.id} value={r.name} />
                  ))}
              </datalist>
            </label>
            <details className="full"><summary>Customer billing details</summary><div className="form-grid"><label>Billing address<input maxLength={500} value={billing.address} onChange={e=>setBilling({...billing,address:e.target.value})}/></label><label>Customer GSTIN<input maxLength={15} value={billing.gstin} onChange={e=>setBilling({...billing,gstin:e.target.value.toUpperCase()})}/></label><label>Customer phone<input maxLength={32} value={billing.phone} onChange={e=>setBilling({...billing,phone:e.target.value})}/></label>{company.tax_mode!=='unregistered'&&<label>Place of supply (state code)<input required pattern="[0-9]{2}" value={billing.place} onChange={e=>setBilling({...billing,place:e.target.value})}/></label>}</div></details>
            {cart.map((row) => (
              <div className="line-card full" key={row.item.id}>
                <div className="line-heading">
                  <strong>{row.item.name}</strong>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Remove ${row.item.name} from cart`}
                    onClick={() =>
                      setCart(cart.filter((r) => r.item.id !== row.item.id))
                    }
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                <div className="form-grid">
                  <label>
                    Quantity
                    <div className="pos-quantity">
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`Decrease ${row.item.name} quantity`}
                        disabled={Number(row.quantity) <= 1}
                        onClick={() =>
                          update(
                            row.item.id,
                            "quantity",
                            String(Number(row.quantity) - 1),
                          )
                        }
                      >
                        <Minus size={14} />
                      </button>
                      <input
                        aria-label={`Quantity for ${row.item.name}`}
                        type="number"
                        min="0.001"
                        step="0.001"
                        required
                        value={row.quantity}
                        onChange={(e) =>
                          update(row.item.id, "quantity", e.target.value)
                        }
                      />
                      <button
                        type="button"
                        className="icon-button"
                        aria-label={`Increase ${row.item.name} quantity`}
                        onClick={() =>
                          update(
                            row.item.id,
                            "quantity",
                            String(Number(row.quantity) + 1),
                          )
                        }
                      >
                        <Plus size={14} />
                      </button>
                    </div>
                  </label>
                  <label>
                    Rate (₹)
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      required
                      value={row.rate}
                      onChange={(e) =>
                        update(row.item.id, "rate", e.target.value)
                      }
                    />
                  </label>
                  <label>
                    Discount (%)
                    <input
                      type="number"
                      min="0"
                      max="100"
                      step="0.01"
                      required
                      value={row.discount}
                      onChange={(e) =>
                        update(row.item.id, "discount", e.target.value)
                      }
                    />
                  </label>
                </div>
              </div>
            ))}
            {!cart.length && (
              <p className="full">Choose an item to add it to this sale.</p>
            )}
            {company?.tax_mode === "regular" && <label className="checkbox-label full">
              <input
                type="checkbox"
                checked={inclusive}
                onChange={(e) => setInclusive(e.target.checked)}
              />
              Prices include GST
            </label>}
            <label className="checkbox-label full">
              <input
                type="checkbox"
                checked={round}
                onChange={(e) => setRound(e.target.checked)}
              />
              Round total to nearest rupee
            </label>
            <label>
              Payment method
              <select
                className="form-select"
                value={method}
                onChange={(e) => setMethod(e.target.value)}
              >
                <option value="cash">Cash</option>
                <option value="bank">Bank / UPI / card</option>
              </select>
            </label>
            {method === "bank" ? (
              <label>
                Receiving bank
                <select
                  className="form-select"
                  value={bank}
                  onChange={(e) => setBank(e.target.value)}
                >
                  {banks.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <label>
                Cash tendered (₹)
                <input
                  type="number"
                  min={preview?.amount || 0}
                  step="0.01"
                  value={tender}
                  onChange={(e) => setTender(e.target.value)}
                  placeholder={preview?.amount || "Exact amount"}
                />
              </label>
            )}
            {preview && (
              <div className="info-box full">
                <strong>Total {money(preview.amount)}</strong>
                <p>
                  GST{" "}
                  {money(
                    Number(preview.data.cgst) +
                      Number(preview.data.sgst) +
                      Number(preview.data.igst),
                  )}
                  {method === "cash" &&
                    (change < 0 ? ` · Still needed ${money(-change)}` : ` · Change ${money(change)}`)}
                </p>
              </div>
            )}
            </fieldset>
            {pending && !busy && <p className="info-box full" role="status">{pendingPostingMessage}</p>}
            <button
              className="button primary full"
              disabled={
                busy ||
                !preview ||
                !cart.length ||
                change < 0 ||
                !["owner", "editor"].includes(company.role)
              }
            >
              {busy ? "Posting sale…" : "Complete sale"}
            </button>
          </form>
        </section>
      </div>
    </>
  );
}
