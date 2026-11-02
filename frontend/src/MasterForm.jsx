import {imageInput} from "./imageInput.js";
import React, { useState } from "react";
import { X } from "lucide-react";

export default function MasterForm({ kind, close, save, record }) {
  const isParty = kind === "party";
  const [form, setForm] = useState({
    party_type: "both",
    payment_terms_days: "",
    low_stock_threshold: "",
    gstin: "",
    address: "",
    phone: "",
    email: "",
    hsn: "",
    unit: "",
    sale_rate: "0",
    purchase_rate: "0",
    gst_rate: "0",
    track_stock: false,
    barcode: "",
    item_type: "goods",
    ...record?.data,
    name: record?.name || "",tax_treatment:record?.data?.tax_treatment || (Number(record?.data?.gst_rate||0)>0?"taxable":"nil_rated"),
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const update=event=>{const key=event.target.name,value=event.target.value;setForm(current=>({...current,[key]:value,...(key==='gst_rate'?{tax_treatment:Number(value)>0?'taxable':current.tax_treatment==='taxable'?'nil_rated':current.tax_treatment}:key==='tax_treatment'&&value!=='taxable'?{gst_rate:'0'}:{})}))};
  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = isParty
        ? {
            party_type: form.party_type,
            gstin: form.gstin,
            address: form.address,
            phone: form.phone,
            email: form.email,
            payment_terms_days: form.payment_terms_days === "" || form.payment_terms_days == null ? null : Number(form.payment_terms_days),
          }
        : {
            ...(form.image_data_url!==undefined?{image_data_url:form.image_data_url}:{}),image_thumbnail:form.image_thumbnail||"",
            hsn: form.hsn,
            unit: form.unit,
            sale_rate: form.sale_rate,
            purchase_rate: form.purchase_rate,
            gst_rate: form.gst_rate,
            track_stock: form.track_stock,
            barcode: form.barcode,
            item_type: form.item_type,tax_treatment:form.tax_treatment,
            low_stock_threshold: form.track_stock && form.item_type !== "services" && form.low_stock_threshold !== "" && form.low_stock_threshold != null ? String(form.low_stock_threshold) : null,
          };
      await save({ kind, name: form.name, data });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      className="overlay"
      onMouseDown={(event) => event.target === event.currentTarget && close()}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Entry form"
      >
        <div className="modal-heading">
          <div>
            <h2>
              {record ? "Edit" : "New"} {isParty ? "party" : "item"}
            </h2>
            <p>
              {record
                ? "Update details for this company."
                : "Add a reusable record to this company."}
            </p>
          </div>
          <button className="icon-button" aria-label="Close" onClick={close}>
            <X size={18} />
          </button>
        </div>
        <form className="form-grid" onSubmit={submit}>
          <label className="full">
            {isParty ? "Party name" : "Item name"}
            <input
              name="name"
              required
              maxLength="120"
              value={form.name}
              onChange={update}
              disabled={!!record}
            />
            {record && (
              <small>
                Names are fixed to preserve existing transaction links.
              </small>
            )}
          </label>
          {isParty ? (
            <>
              <label>
                Party type
                <select
                  className="form-select"
                  name="party_type"
                  value={form.party_type}
                  onChange={update}
                >
                  <option value="both">Customer and supplier</option>
                  <option value="customer">Customer</option>
                  <option value="supplier">Supplier</option>
                </select>
              </label>
              <label>
                GSTIN
                <input
                  name="gstin"
                  maxLength="15"
                  value={form.gstin}
                  onChange={update}
                  placeholder="Optional"
                />
              </label>
              <label>
                Phone
                <input
                  name="phone"
                  type="tel"
                  maxLength="32"
                  value={form.phone}
                  onChange={update}
                />
              </label>
              <label>
                Email
                <input
                  name="email"
                  type="email"
                  maxLength="254"
                  value={form.email}
                  onChange={update}
                />
              </label>
              <label className="full">Default payment terms (days)<input name="payment_terms_days" type="number" min="0" max="3650" step="1" value={form.payment_terms_days ?? ""} onChange={update} placeholder="No default" /><small>Optional. Net 0 means due on the document date. Existing documents keep their saved due dates.</small></label>
              <label className="full">
                Address
                <input
                  name="address"
                  maxLength="500"
                  value={form.address}
                  onChange={update}
                />
              </label>
            </>
          ) : (
            <>
              <div className="full"><label>Item image<input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={async e=>{const file=e.target.files?.[0];if(!file)return;setBusy(true);setError('');try{const [image,thumbnail]=await Promise.all([imageInput(file,600,64000),imageInput(file,160,15000)]);setForm(current=>({...current,image_data_url:image,image_thumbnail:thumbnail}))}catch(err){setError(err.message)}finally{setBusy(false);e.target.value=''}}}/></label>{(form.image_data_url||form.image_thumbnail)&&<><img src={form.image_data_url||form.image_thumbnail} alt="Item preview" style={{maxWidth:150,maxHeight:120}}/><button className="link" type="button" onClick={()=>setForm({...form,image_data_url:'',image_thumbnail:''})}>Remove item image</button></>}</div>
              <label>
                Item type
                <select
                  className="form-select"
                  name="item_type"
                  value={form.item_type}
                  onChange={update}
                >
                  <option value="goods">Goods</option>
                  <option value="services">Services</option>
                </select>
              </label>
              <label>
                Barcode
                <input
                  name="barcode"
                  maxLength={80}
                  value={form.barcode}
                  onChange={update}
                />
              </label>
              <label>
                HSN / SAC
                <input
                  name="hsn"
                  maxLength="16"
                  value={form.hsn}
                  onChange={update}
                />
              </label>
              <label>
                Unit
                <input
                  name="unit"
                  maxLength="24"
                  value={form.unit}
                  onChange={update}
                  placeholder="e.g. pcs"
                />
              </label>
              <label>
                Sale rate (₹)
                <input
                  name="sale_rate"
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.sale_rate}
                  onChange={update}
                />
              </label>
              <label>
                Purchase rate (₹)
                <input
                  name="purchase_rate"
                  type="number"
                  min="0"
                  step="0.01"
                  value={form.purchase_rate}
                  onChange={update}
                />
              </label>
              <label>GST treatment<select className="form-select" aria-label="Item GST treatment" name="tax_treatment" value={form.tax_treatment} onChange={update}><option value="taxable">Taxable</option><option value="nil_rated">Nil rated</option><option value="exempt">Exempt</option><option value="non_gst">Non-GST supply</option></select></label>
              <label>
                GST rate (%)
                <input
                  name="gst_rate"
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  value={form.gst_rate}
                  onChange={update}
                />
              </label>
              <label className="full stock-toggle">
                <input
                  type="checkbox"
                  checked={form.track_stock}
                  disabled={!!record}
                  onChange={(event) =>
                    setForm({ ...form, track_stock: event.target.checked })
                  }
                />{" "}
                Track stock quantities for this item
                {record && " (fixed after creation)"}
              </label>
              {form.track_stock && form.item_type !== "services" && <label className="full">Low-stock threshold<input name="low_stock_threshold" type="number" min="0" step="0.001" value={form.low_stock_threshold ?? ""} onChange={update} placeholder="Disabled" /><small>Alerts when on-hand stock is at or below this quantity. Blank disables alerts. Changing this never posts stock or accounting entries.</small></label>}

            </>
          )}
          {error && <div className="error full">{error}</div>}
          <div className="modal-actions full">
            <button type="button" className="button secondary" onClick={close}>
              Cancel
            </button>
            <button className="button primary" disabled={busy}>
              {busy ? "Saving…" : `Save ${isParty ? "party" : "item"}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
